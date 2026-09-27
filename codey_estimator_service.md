# Codey-Estimator Integration — Service Layer, API, UI & Delivery (Phase B9.2+)

**Status: scoped 2026-09-27, PLAN ONLY — nothing in this document is built.**
Written while B9.1 (`codey_estimator_schema.md`) is code-complete and
code-reviewer-approved but **not yet live-verified or merged to `main`**. This
round's build does not start until a session with device access confirms
B9.1 and merges it — this document scopes the *next* round so that work is
ready to route through the pipeline the moment B9.1 unblocks.

This is a spoke, not a second hub — `CODEY_MASTER_PLAN.md` remains the single
authoritative plan (§0). Registered there as an extension of **Phase B9**
(§6.13, Appendix A), same pattern as `sales_rep_portal.md` (B8) and
`codey_estimator_schema.md` (B9.1). Field lists already defined in
`codey_estimator_schema.md` are **not repeated here** — this document adds
the service methods, routes, and UI that sit on top of that schema.

## 0. What already exists — read, not assumed

Verified 2026-09-27 by reading the real files on `feat/estimator-phase3-schema`
(`CLAUDE.md` rule 12), not from the companion library's plan alone.

- **Schema is real, on this branch**: `restoricon_core/database.py` has the
  rebuilt `estimates` table (`database.py:220-286`, `created_by_user_id`,
  `assigned_to_user_id`, `workflow_status`, `current_version_id`,
  `accepted_version_id`, `converted_project_id`, `contract_id`, etc.),
  `estimate_versions` (`database.py:288-336`, integer-cents,
  `trg_estimate_versions_locked_immutable`), `estimate_line_items`
  (`database.py:350-422`, three lock-enforcement triggers),
  `estimate_share_links` (`database.py:426-453`, `token_hash`-only), and
  `estimate_decisions` (`database.py:462-479`, append-only). `users` gained
  `requires_estimate_approval` (`database.py:41-43`). `documents` gained
  `estimate_id`/`customer_visible` per the schema doc §1's additive block.
- **RBAC is real, on this branch**: `restoricon_core/auth.py:220-225` declares
  the six new permission constants (`PERM_READ_ALL_ESTIMATES`,
  `PERM_READ_ESTIMATE_COSTS`, `PERM_REASSIGN_ESTIMATES`,
  `PERM_SEND_ESTIMATES`, `PERM_APPROVE_ESTIMATES`, `PERM_MANAGE_PRICE_BOOK`),
  the legacy `PERM_READ_ESTIMATES`/`PERM_WRITE_ESTIMATES`/
  `PERM_READ_OWN_ESTIMATES` still exist unchanged (`auth.py:106-108`), and
  every role's grants are wired (`auth.py:242-546`).
- **The service layer has NOT caught up to the new schema/RBAC.**
  `CRMService.create_estimate`/`get_estimate`/`list_estimates`/
  `_row_to_estimate` (`crm_service.py:2302-2425`) still write/read only the
  *legacy* `Estimate` dataclass columns (`estimate_number`, `subtotal`,
  `materials_cost`, …, `status`) — nothing touches `created_by_user_id`,
  `workflow_status`, `estimate_versions`, or `estimate_line_items`. Two real,
  currently-shipped gaps this round fixes:
  1. `create_estimate`'s `POST /api/v1/estimates` route does
     `Estimate(**json_body)` (`routes.py:1070`) — **the client supplies
     `estimate_number` directly in the request body today.** This is the
     exact F1/F5-shaped bug the task that added B9.1's RBAC was chasing:
     nothing stops a caller (including `ai_agent`) from setting
     `estimate_number="EST-2026-0001"` to collide with, or spoof, a real
     estimate. Fixed below (§1.1) by making the service, not the client, own
     both the number and the creator identity.
  2. `get_estimate`/`list_estimates` gate on `PERM_READ_ESTIMATES OR
     PERM_READ_OWN_ESTIMATES` only — **there is no ownership narrowing at
     all** for a plain `sales` user: any actor holding `PERM_READ_ESTIMATES`
     (admin, manager, sales, sales_manager, project_manager, ai_agent — see
     `auth.py:242-546`) sees every estimate in the table, full stop. B9.1's
     schema doc explicitly flagged this as deferred: *"`ROLE_SALES` … stays
     scoped to own/assigned/unclaimed once a future service-layer phase adds
     real narrowing"* — this is that phase.
- **`_row_to_estimate`'s existing cost redaction is role-string-keyed, not
  permission-keyed** (`is_customer = actor_role in (ROLE_CUSTOMER,
  ROLE_TECHNICIAN)`, `crm_service.py:2362`) — pre-dates `PERM_READ_ESTIMATE_COSTS`
  entirely. B9.2 replaces this with the permission check, which is also how
  D9's revised answer (see §2 below) gets implemented correctly instead of
  by another hardcoded role list.
- **`codey_estimator`'s pure library is complete and tested** — `calculate()`
  (`Codey-Estimator/src/codey_estimator/calc/engine.py:330`, pure function,
  `EstimateInput -> EstimateResult`), `LineInput`/`MaterialInput`/
  `LaborInput`/`EquipmentInput`/`SubcontractorInput` (`dto.py:37-96`, map
  1:1 onto `estimate_line_items`' columns — confirmed by reading both side
  by side, not assumed), and `CustomerEstimateView`/`to_customer_view()`
  (`dto.py:166-226`, allow-list serializer, forbidden-keys test already
  exists in that repo). **B9.2+ integrates this library, it does not
  reimplement any of its math** — every dollar figure an estimate shows
  anywhere in Codey-OS is produced by calling `calculate()`, never by
  service-layer or route-layer arithmetic.
- **`NotificationService`** (`restoricon_core/services/notification_service.py`,
  57 lines total) is a thin POST-to-Aigentik wrapper: `send_email(to, subject,
  body, html=None)` → `POST {aigentik_url}/send-email`. No templating, no
  queue, no retry beyond the 2-second timeout already in `_post_request`.
  Estimate-send/decision emails reuse this exact method, building the
  subject/body/html string in the service layer — no new notification
  mechanism.
- **No numbering generator exists anywhere in this codebase today** for
  `estimate_number` or `contract_number` — both are presently
  client-/caller-supplied strings passed straight into the dataclass
  (confirmed: `grep` for an in-repo generator function found none; contrast
  `invoice_number`, which *is* server-generated,
  `f"INV-{now[:10].replace('-','')}-{secrets.token_hex(2).upper()}"`,
  `crm_service.py:2676`). §1 designs the first one.
- **No public capability-token (path-based, hash-stored) precedent exists.**
  The only existing bearer-token mechanisms are the session `api_tokens`
  table (raw token stored, `auth.py:905-913`) and the `?token=`
  query-param fallback for authenticated routes (`routes.py:493-498`).
  Confirmed by grep: no `token_hash`, no `/e/`-style path route, nothing
  matching the share-link shape anywhere in `restoricon_core` before B9.1's
  `estimate_share_links` table. **§4 below is genuinely new infrastructure,
  not a reuse of an existing pattern** — stated explicitly since the
  companion library's plan (§18/§24) calls this out as a hard requirement
  ("the token sits in the path, not `?token=`") precisely because the
  existing pattern must NOT be reused for it.

## 1. `EstimateService` — new file, not a `crm_service.py` section

**Decision: new file `restoricon_core/services/estimate_service.py`, not a
new `# ESTIMATES` block appended to `crm_service.py`.**

Why, following this codebase's own precedent rather than inventing a rule:
`crm_service.py` is already 4,392 lines — larger than `web_surfaces.py`'s
single-file budget discomfort that motivated B8's own `/sales`,`/pm`,`/tech`
surfaces being separate render functions rather than more `render_admin_surface()`
branches. `sales_rep_portal.md` §5's B8.7 phase raised exactly this question
for commissions and left it as "decide at implementation time" — this
document is that decision, made now because the estimate domain is large
enough on its own to warrant it up front: 4 tables, a locking workflow, a
numbering generator, a calc-engine integration point, and a capability-token
delivery mechanism is a bigger unit of concern than any existing single
`# SECTION` in `crm_service.py` (compare `# CONTRACTS / PROPOSALS`, the
next-largest section, at ~200 lines for 2 tables and no state machine).
`EstimateService` is constructed the same way `OperationsService`/
`FinanceService` already are (`routes.py:347-348`:
`OperationsService(crm_service.db, audit_service)`) — `EstimateService(db,
audit_service, notification_service)`, sharing the one `DatabaseManager` and
the one `AuditService`, never a second copy of either. It imports
`codey_estimator` (the only place in `restoricon_core` that does) and never
touches SQLite directly from outside its own module, same boundary
`crm_service.py` already keeps for every other domain.

New dataclasses in `models.py` (same file every other domain's dataclasses
live in — `Estimate`, `Contract`, `Invoice` are already there,
`models.py:513-553`): `EstimateHeader`, `EstimateVersion`,
`EstimateLineItem`, `EstimateShareLink`, `EstimateDecision`. Field names and
types are the exact columns `codey_estimator_schema.md` §1/§2 already
specifies — **not restated here**, per this document's own no-duplication
rule. The **existing** `Estimate` dataclass (`models.py:513-533`) is left
completely untouched — it is still what `line_items_json`/legacy columns
serialize to, for any pre-B9.1 caller. `EstimateHeader` is a new,
additional dataclass for the rebuilt table's new columns; `_row_to_estimate`
stays as the legacy-shape reader `CRMService` still owns (nothing calls
`CRMService.create_estimate`/`get_estimate`/`list_estimates` after this round
except possibly the pricing-tables-deferred `ai_agent` legacy path, if any —
confirm no live caller during implementation and delete them if genuinely
dead, logging the finding rather than silently dropping them, per rule 8).

### 1.1 `create(header: EstimateHeaderInput, actor: AuthContext) -> EstimateHeader`

```python
def create(
    self,
    *,
    customer_id: int,
    project_id: int | None,
    opportunity_id: int | None,
    lead_id: int | None,
    property_id: int | None,
    title: str | None,
    terms: str | None,
    customer_notes: str | None,
    expires_at: str | None,      # ISO date; defaults to now+30d if None (D10)
    assigned_to_user_id: int | None,  # defaults to actor.user_id if None
    actor: AuthContext,
) -> EstimateHeader:
```

- Requires `PERM_WRITE_ESTIMATES` (unchanged permission, still the write
  gate — B9.1 did not add a separate `PERM_CREATE_ESTIMATES`).
- **`created_by_user_id` is set from `actor.user_id`. `created_by_name` is
  snapshotted from `actor`'s `full_name` at call time (looked up via
  `self.auth.get_user_by_id(actor.user_id)`, mirroring the pattern
  `crm_service.py` already uses elsewhere for name snapshots). Neither field
  is ever accepted as an input parameter** — the method signature has no
  `created_by_user_id`/`created_by_name` parameter at all, so there is no
  code path by which a request body could set them. This is the actual fix
  for §0's finding 1: the route layer (§3) parses only the fields this
  signature accepts; anything else in the JSON body is silently ignored,
  not merged in. (Contrast the current `Estimate(**json_body)` at
  `routes.py:1070`, which accepts every key.)
- `estimate_number` is generated by `_next_estimate_number()` (§2), never a
  parameter.
- `workflow_status` starts at `DRAFT` always — not a parameter.
- Inserts the `estimates` header row and, in the **same transaction**,
  creates `estimate_versions` version 1 (`is_locked=0`,
  `calc_engine_version=codey_estimator.calc.CALC_ENGINE_VERSION`, all cost/
  sell columns 0 until the first line is added — an estimate can exist with
  zero lines as a true draft) and sets `current_version_id` to it. One
  `conn` transaction, one `self.db.get_connection()` call, matching the
  `create_estimate`/`create_contract` transaction shape exactly
  (`crm_service.py:2314-2346`).
- Audit: `action="create", entity_type="estimate"`,
  `build_audit_details(after=header.to_dict())`.
- **Exit-criterion-relevant test case**: POST body includes
  `"created_by_user_id": 999, "estimate_number": "EST-FAKE"` — assert the
  created row's `created_by_user_id` is the actor's real id and
  `estimate_number` is server-generated, not `"EST-FAKE"`.

### 1.2 `get(estimate_id, actor) -> EstimateHeader | None` and `list(...)`

```python
def get(self, estimate_id: int, actor: AuthContext, *, include_lines: bool = False) -> EstimateHeader | None
def list(
    self, actor: AuthContext, *,
    customer_id=None, project_id=None, assigned_to_user_id=None,
    created_by_user_id=None, workflow_status=None,
    date_from=None, date_to=None, q=None,
    limit: int = 50, offset: int = 0,
) -> List[EstimateHeader]
```

**Real ownership narrowing (§0's finding 2, the actual fix):**
- `actor.has_permission(PERM_READ_ALL_ESTIMATES)` → no `WHERE` narrowing
  beyond the caller's own filters (admin, manager, sales_manager, ai_agent —
  per `auth.py:242-546`/`544-546`).
- Else, `actor.has_permission(PERM_READ_ESTIMATES) or
  actor.has_permission(PERM_READ_OWN_ESTIMATES)` (plain `sales`,
  `project_manager`) → the query adds `AND (created_by_user_id = ? OR
  assigned_to_user_id = ?)` bound to `actor.user_id` **both times** — a rep
  sees what they created or what they're assigned, same "own or assigned"
  shape `sales_rep_portal.md` §5's B8.2 exit criterion already establishes
  for leads/opportunities/tasks (`NEW-533`/`NEW-534` precedent). **Open
  decision, flagged not decided — see §8 item 1**: whether an *unclaimed*
  estimate (`assigned_to_user_id IS NULL`, can this even occur given §1.1
  defaults `assigned_to_user_id` to the creator? — only via a future
  reassign-to-null action, if ever allowed) should also be visible to any
  `sales` actor the way `NEW-534`'s claim workflow makes unclaimed
  leads/opportunities visible-but-claimable. This document does not decide
  it because it's a workflow policy question, not an implementation detail.
- `ROLE_CUSTOMER` → forced to `customer_id = actor.customer_id`, exactly the
  existing pattern (`crm_service.py:2395-2396`), and only via
  `PERM_READ_OWN_ESTIMATES`.
- **Cost/margin gating** (D9's revised answer — sales, sales_manager,
  manager, admin ALL see cost on every estimate they can otherwise see,
  editing stays admin/manager-only): the DTO returned to the route layer
  includes `cost_total_cents`/`gross_profit_cents`/`gross_margin_bp`
  (from the current version) only if `actor.has_permission(PERM_READ_ESTIMATE_COSTS)`
  — a single permission check, not a role-string list, replacing
  `_row_to_estimate`'s current `is_customer` hardcoding (§0). This
  correctly implements D9 without re-deriving it: `ROLE_SALES` already gets
  `PERM_READ_ESTIMATE_COSTS` by default per `codey_estimator_schema.md` §4's
  table, and that grant already applies to every estimate the narrowing
  above lets them see — D9 said "not just their own" about cost visibility,
  and this design delivers that (a sales rep who can see a colleague's
  *assigned* estimate — because they're a joint assignee, or via a future
  admin action — sees its cost too), while row-level visibility narrowing
  (a separate, correct concern: whether they can see the estimate AT ALL)
  stays scoped per the paragraph above, unchanged from B9.1's own stated
  intent.
- `include_lines=True` on `get()` additionally loads the current version's
  `estimate_line_items`, ordered by `sort_order`. `list()` never includes
  lines (matches `list_estimates`'s existing summary-row shape).

### 1.3 `update_header(estimate_id, updates: dict, actor) -> EstimateHeader`

Allow-list pattern, following `ALLOWED_UPDATE_FIELDS`/`update_subcontractor`
exactly (`crm_service.py:3386-3419`):

```python
ALLOWED_UPDATE_FIELDS = {
    "title", "terms", "customer_notes", "expires_at",
    "property_id", "opportunity_id", "lead_id",
}
```

- Requires `PERM_WRITE_ESTIMATES`.
- **Only while the estimate's `current_version_id` points at an unlocked
  version** (i.e., `workflow_status in ('DRAFT', 'INTERNAL_REVIEW',
  'CHANGES_REQUESTED')`) — else raise `ValueError("cannot update a
  header field once the current version is locked; use revise()")`. This
  is the "update only while draft/unlocked" rule the task asked for,
  expressed as a version-lock check rather than a separate hand-maintained
  status list, so it can't drift from the trigger-enforced immutability
  §1.6 relies on.
- `created_by_user_id`, `created_by_name`, `assigned_to_user_id`,
  `workflow_status`, `estimate_number` are explicitly **not** in the
  allow-list — reassignment and transitions are their own methods (§1.4/
  §1.5), matching why `update_subcontractor` excludes
  `qualification_status`.
- Old/new audit via `build_audit_details(before=..., after=..., fields=...)`,
  same shape as `update_project`'s pattern.

### 1.4 `reassign(estimate_id, new_assignee_user_id, actor) -> EstimateHeader`

- Requires `PERM_REASSIGN_ESTIMATES` — the `PERM_REASSIGN_PROJECT_STAFF`
  precedent (`crm_service.py:633`) named in this task's brief.
- Validates `new_assignee_user_id` refers to an active user with a role that
  can hold estimates (`ROLE_SALES`, `ROLE_SALES_MANAGER`,
  `ROLE_PROJECT_MANAGER`, `ROLE_MANAGER`, `ROLE_ADMIN`) — reject reassigning
  to a technician or customer account with a `ValueError`.
- Audit: `action="assign"`, `build_audit_details(before={"assigned_to_user_id":
  old}, after={"assigned_to_user_id": new})` — old/new, not a full-row dump,
  matching the B6.2 standard `sales_rep_portal.md` B8.13 holds every write
  path to.

### 1.5 The workflow state machine — `transition(estimate_id, new_status, actor, **kwargs) -> EstimateHeader`

**Exact machine (per D5, `Codey-Estimator/docs/DECISIONS.md` line 13, already
answered and binding):**

```
DRAFT ──(submit_for_review)──► INTERNAL_REVIEW ──(approve)──► APPROVED_INTERNAL
  │                                    │                              │
  │                                    └──(reject_review)──► DRAFT     │
  │                                                                    │
  └─────────────────────(send, if no review required)─────────────────┤
                                                                        ▼
                                                                      SENT ──(view, system/customer-triggered)──► VIEWED
                                                                        │                                            │
                                                                        ├──(expire, time-based)──────────────► EXPIRED
                                                                        ├──(cancel)──────────────────────────► CANCELLED
                                                                        └────────────┬───────────────────────────────┘
                                                                                     ▼
                                                        ACCEPTED ◄──(customer decision)──┤
                                                        DECLINED ◄──(customer decision)──┤
                                              CHANGES_REQUESTED ◄──(customer decision)───┘
                                                        │
                                                        ▼ (revise() clones a new version, per §1.6)
                                            back to DRAFT on the NEW version, old version stays ACCEPTED/…/superseded
                                                        │
                                              ACCEPTED ──(convert)──► CONVERTED
```

Allowed transitions table (the single source of truth the method enforces —
anything not listed is a `ValueError`):

| From | To | Who / permission | Side effects |
|---|---|---|---|
| `DRAFT` | `INTERNAL_REVIEW` | creator or assignee, `PERM_WRITE_ESTIMATES` | none |
| `DRAFT` | `SENT` | `PERM_SEND_ESTIMATES`, **only if** the assignee's `users.requires_estimate_approval = 0`; else refused with a `ValueError` naming the review requirement | locks current version (§1.6), creates share link (§4) |
| `INTERNAL_REVIEW` | `APPROVED_INTERNAL` | `PERM_APPROVE_ESTIMATES` | none |
| `INTERNAL_REVIEW` | `DRAFT` | `PERM_APPROVE_ESTIMATES` (a rejection is also a review action) | `comment` kwarg required, stored in the audit `change_summary` |
| `APPROVED_INTERNAL` | `SENT` | `PERM_SEND_ESTIMATES` | locks current version, creates share link |
| `SENT` | `VIEWED` | **not actor-driven** — called internally by the public view route (§5) with `actor=None`/a synthetic system actor, never exposed as a directly callable transition from an authenticated staff route | sets `last_viewed_at`/`first_viewed_at` on the share link, not the estimate row's own timestamp columns (avoids two sources of truth) |
| `SENT` or `VIEWED` | `ACCEPTED` / `DECLINED` / `CHANGES_REQUESTED` | **not actor-driven** — called internally by the decision-recording method (§1.7), which is what the public/portal accept-decline-changes route actually calls | creates the `estimate_decisions` row; `ACCEPTED` also sets `accepted_version_id`/`accepted_at` and, per D7, triggers contract creation (§1.9) |
| `SENT` or `VIEWED` | `EXPIRED` | system-driven only — run by the B9.2b expiry-sweep thread (§9 item 3), never a directly callable transition from any route | none beyond the status change, individually audit-logged per row by the sweep |
| any of `DRAFT`/`INTERNAL_REVIEW`/`APPROVED_INTERNAL`/`SENT`/`VIEWED` | `CANCELLED` | `PERM_WRITE_ESTIMATES` (creator/assignee) or `PERM_REASSIGN_ESTIMATES` (manager-tier) | `comment` kwarg required |
| `ACCEPTED` | `CONVERTED` | handled by `convert()` (§1.9), not a bare `transition()` call | creates/links Contract + Project |

- Every transition call audits `action="transition"`,
  `change_summary=f"{old} -> {new}"`, `details=build_audit_details(before=
  {"workflow_status": old}, after={"workflow_status": new}, snapshot=
  {"comment": comment} if comment else None)` — matches §20 of the companion
  plan (`ARCHITECTURE_PLAN.md:806-808`) verbatim.
- `ai_agent` can reach `DRAFT`/`INTERNAL_REVIEW` only (create + submit for
  review) — it structurally cannot reach `SENT` because it never holds
  `PERM_SEND_ESTIMATES` (`codey_estimator_schema.md` §4's table, D11). This
  is enforced by the permission check on the `DRAFT -> SENT` /
  `APPROVED_INTERNAL -> SENT` rows above, not a separate `ai_agent`-specific
  branch — one mechanism, not two ways to reach the same guarantee.

### 1.6 Versioning — `revise(estimate_id, actor) -> EstimateVersion`

- Requires `PERM_WRITE_ESTIMATES`.
- Only callable when the estimate's current version `is_locked = 1`
  (else raise — editing an unlocked version happens through the line-item
  methods directly, no explicit "revise" step needed, per §19 of the
  companion plan).
- Clones the locked version's header snapshot fields
  (`terms_snapshot`, `customer_notes_snapshot` become the new version's
  starting `terms_snapshot`/`customer_notes_snapshot`, copied from the
  *estimate's current* `terms`/`customer_notes` at clone time — not
  re-copied from the old version, so a header edit made via §1.3 while
  reviving shows up) and every line in `estimate_line_items` **verbatim**,
  including all snapshot columns (`unit_cost_cents`,
  `retailer_code_snapshot`, etc.) — prices do **not** silently refresh, per
  the companion plan's explicit "prices don't silently refresh" rule
  (`ARCHITECTURE_PLAN.md:786`).
- New version gets `version_number = MAX(version_number) + 1` for that
  `estimate_id`, `is_locked = 0`, `locked_reason = NULL`,
  `calc_engine_version` re-stamped to the **current**
  `codey_estimator.calc.CALC_ENGINE_VERSION` at revise time (the old
  version's own `calc_engine_version` is untouched, preserving its
  historical re-derivability).
- Sets the estimate's `current_version_id` to the new version and
  `workflow_status` back to `DRAFT`. The old version's `locked_reason`
  becomes `'superseded'` (an `UPDATE` — the immutability trigger
  (`trg_estimate_versions_locked_immutable`) fires on this exact `UPDATE`
  too, since it's `BEFORE UPDATE ... WHEN OLD.is_locked = 1` with no
  exception for a `locked_reason`-only change — **so this UPDATE must be
  the one exception the service issues via a documented, narrow bypass**:
  either (a) the trigger is scoped to reject writes to any column *except*
  `locked_reason` (a small `WHEN` clause change, itself a rule-4 schema
  edit needing its own review), or (b) `revise()` never updates the old
  row's `locked_reason` at all and "superseded" is instead *derived* at
  read time (`version_number < estimate.current version's number`, `is_locked=1`
  ⇒ superseded) rather than stored. **Recommend (b)** — it needs no schema
  change, and it can't drift out of sync with `current_version_id` the way
  a stored flag could. Flagged here because it reads as a discrepancy
  against the companion plan's prose ("marks earlier sent versions
  superseded") if not called out: the *fact* is still true and visible,
  just computed, not stored. If the implementer disagrees and wants (a),
  that goes back through project-architect + code-reviewer as its own
  rule-4 schema change, not decided ad hoc mid-implementation.
- An "update prices to current" action is a **separate, explicit,
  audited** per-line method (`refresh_line_price(line_id, actor)`) called
  by the estimator after `revise()`, never automatic — matches
  `ARCHITECTURE_PLAN.md:786-787` exactly. Deferred to the pricing-tables
  phase in practice (there's no live price source to refresh *from* until
  then) but the method signature/audit shape is specified now so B9.2's
  line-item CRUD (§1.8) doesn't need a second review pass later just to add
  it.

### 1.7 Decisions — `record_decision(...)`

```python
def record_decision(
    self, *, estimate_version_id: int, decision: str,  # 'accepted'|'declined'|'changes_requested'
    signer_name: str | None, signature_data: str | None, comment: str | None,
    share_link_id: int | None, customer_user_id: int | None,
    ip: str, user_agent: str,
) -> EstimateDecision
```

- Called only from the public share-link route or the authenticated
  `/portal` route (§4) — never has an `actor: AuthContext` parameter,
  because a share-link viewer isn't an authenticated actor at all (this
  mirrors why `transition()`'s customer-facing rows aren't actor-gated
  either).
- **D10, enforced here, not just documented**: if `decision == 'accepted'`,
  `signer_name` and a `consent_text_snapshot` (a fixed, versioned consent
  string baked into the service, e.g. `CONSENT_TEXT_V1`) are **required** —
  `ValueError` if either is missing/blank. `signature_data` stays optional.
  Exactly one of `share_link_id`/`customer_user_id` must be set (`ValueError`
  if both or neither).
- Inserts the `estimate_decisions` row, then calls `transition()` on the
  parent estimate with the corresponding `workflow_status`
  (`accepted`→`ACCEPTED`, etc.) using a synthetic system actor (or an
  internal transition path that skips the normal permission check — same
  "not actor-driven" carve-out §1.5's table already states for this row).
- On `accepted`: sets `estimates.accepted_version_id`/`accepted_at`, and —
  per D7 — calls `_create_contract_from_estimate()` (§1.9) in the **same
  transaction** as the decision insert and the status transition, so an
  accepted estimate can never exist without its contract half-created (or
  neither exists, if any step fails — one `BEGIN`, one `COMMIT`).
- Confirmation email via `NotificationService.send_email` (§0) to the
  customer, and a separate notification to the assignee — both **after**
  the transaction commits, never inside it (matches the existing pattern of
  never holding a DB transaction open across a network call).

### 1.8 Line items — CRUD scoped to the unlocked current version

```python
def add_line(self, estimate_id: int, line: LineInputDict, actor: AuthContext) -> EstimateLineItem
def update_line(self, line_id: int, updates: dict, actor: AuthContext) -> EstimateLineItem
def remove_line(self, line_id: int, actor: AuthContext) -> None
def reorder_lines(self, estimate_id: int, ordered_line_ids: list[int], actor: AuthContext) -> None
```

- All four require `PERM_WRITE_ESTIMATES` and operate only on the
  estimate's *current* version — if it's locked, the three lock-enforcement
  triggers (`database.py:406-422`) are the backstop, but the service checks
  `is_locked` first and raises a clean `ValueError` rather than letting a
  raw `sqlite3.IntegrityError`/trigger-`RAISE(ABORT)` surface to the API
  layer as a 500.
- **No cost/sell column on `estimate_line_items` is ever set by
  `add_line`/`update_line` directly.** The caller supplies only the
  *inputs* (`quantity`, `unit_cost_cents`, `waste_pct_bp`,
  `material_markup_bp`, `labor_qty`, `labor_bill_rate_cents`, …, the exact
  input-side columns per `codey_estimator_schema.md` §2's table). After the
  write, the service **re-runs `calculate()` over every line in the
  version** and writes the returned `material_cost_cents`,
  `labor_cost_cents`, `cost_total_cents`, `sell_total_cents`, `tax_cents`,
  `line_total_cents` (per line) and the version's own aggregate columns
  (`subtotal_sell_cents`, `total_cents`, `gross_profit_cents`, etc.) back in
  the same transaction. **This is the exact "server-authoritative totals"
  requirement** (`ARCHITECTURE_PLAN.md:949`, plan §24) — the UI never
  computes or sends a total; every persisted dollar figure came out of
  `codey_estimator.calc.calculate()` on the server, in this one call path.
- Line-level audit: `entity_type="estimate_line"`, `action` one of
  `add`/`update`/`remove`, `build_audit_details` with old/new for
  `update_line`, matching §20's `estimate_line` event list
  (`ARCHITECTURE_PLAN.md:809-810`).
- `price_override_cents` requires `override_reason` (non-blank) — enforced
  here, matching the companion plan's guard (`ARCHITECTURE_PLAN.md:677`,
  §24's "Overrides require a reason and are audited").

### 1.9 `preview(estimate_id, actor) -> EstimateResult` and `convert(estimate_id, actor) -> dict`

- `preview()`: re-runs `calculate()` over the current version's lines
  **without persisting anything** — the read-only endpoint the staff UI's
  "review totals" step (§25 of the companion plan, §5 below) calls on every
  keystroke/line-add before the estimator hits Save. Requires
  `PERM_WRITE_ESTIMATES` (same as viewing your own draft).
- `convert()` — per plan §22, gated on **D7 (already answered: yes,
  estimate → contract → job)**:
  - Requires `workflow_status == 'ACCEPTED'`. `PERM_WRITE_ESTIMATES` plus
    ownership/assignment (or `PERM_READ_ALL_ESTIMATES`-tier).
  - **Idempotent**: if `converted_project_id` is already set, returns the
    existing `{contract_id, project_id}` pair rather than creating a
    second one — matches `ARCHITECTURE_PLAN.md:895-897` exactly.
  - The contract half is **already created** by `record_decision()` at
    acceptance time (§1.7) — `convert()`'s job is the **Project** half
    only: if the estimate's `opportunity_id` already has a linked
    `project_id` (checked via `CRMService.get_opportunity`), link to it;
    else create a new `Project` via the existing `CRMService.create_project`
    with `contract_amount` = the accepted version's `total_cents` (converted
    to the legacy float column `Project` still uses — a cents→float
    conversion happens here, once, at the one boundary where the new
    integer-cents world meets the old REAL-money world; this is the only
    place in this round money crosses that boundary, and it's called out
    explicitly rather than silently normalized) and `estimated_cost` from
    `cost_total_cents`.
  - **Open policy question, flagged not decided — see §8 item 5**: whether
    `convert()` should also require a *signed* contract (not just a
    created-but-unsigned one) before creating the Project, per the
    companion plan's own conditional ("if the B8.12 handoff rule is
    adopted, it also requires a signed contract" — B8.12 is designed in
    `sales_rep_portal.md` but **not yet built**). This document does not
    assume B8.12's gate exists yet, so `convert()` as specified here does
    NOT require a signature — but that is a real production-readiness gap
    (a Project could exist against an unsigned contract) that Ish should
    rule on before B9.8 (§7 below) ships.
  - `properties` (B8.1) does **not exist yet** (confirmed,
    `codey_estimator_schema.md` §1's note) — `convert()` does not touch
    `property_id` beyond copying it onto the new `Project` row if
    `Project` already has a nullable `property_id`-shaped column (it
    doesn't today; if B8.1 lands first, this is a one-line addition, not a
    blocker for this phase).
  - Audit: `action="convert"`, `entity_type="estimate"`, snapshot of
    `{contract_id, project_id}`.

## 2. Estimate numbering — race-safe, server-generated

**Design: a per-year sequence table, incremented inside the same
`BEGIN IMMEDIATE` transaction as the estimate insert — not a `MAX(id)+1`
read, and not a bare in-memory counter.**

Why not `MAX(estimate_number)+1` (or `MAX(id)+1`): this project has a
documented history of exactly this failure shape — the `NEW-534`
claim-workflow race (`sales_rep_portal.md` §4a item 2) — where a
read-then-write with no atomic guard let two callers land on the same
outcome. A `SELECT MAX(...)` followed by an `INSERT` has the identical
shape: two concurrent `create()` calls can both read the same max and both
insert the same next number, and `estimate_number`'s `UNIQUE NOT NULL`
constraint would only turn that race into a 500 for the loser, not resolve
it cleanly.

**New table** (added to `_SCHEMA_SQL`, its own small rule-4 schema addition
— flag to code-reviewer alongside whatever else lands in the same round):

```sql
CREATE TABLE IF NOT EXISTS estimate_number_sequences (
    year INTEGER PRIMARY KEY,
    next_seq INTEGER NOT NULL DEFAULT 1
);
```

**`_next_estimate_number()` implementation shape:**

```python
def _next_estimate_number(self, conn: sqlite3.Connection, year: int) -> str:
    # Caller already holds this conn inside a BEGIN IMMEDIATE transaction
    # (the same transaction the estimate row itself is inserted in) --
    # SQLite's write lock, acquired at BEGIN IMMEDIATE, is what makes this
    # safe under real concurrent writers (WAL mode allows concurrent
    # readers, but only one writer at a time; BEGIN IMMEDIATE claims that
    # writer lock up front instead of on first write, closing the
    # upgrade-race window NEW-534 was bitten by).
    conn.execute(
        "INSERT INTO estimate_number_sequences (year, next_seq) VALUES (?, 2) "
        "ON CONFLICT(year) DO UPDATE SET next_seq = next_seq + 1;",
        (year,),
    )
    row = conn.execute(
        "SELECT next_seq FROM estimate_number_sequences WHERE year = ?;", (year,)
    ).fetchone()
    seq = row["next_seq"] - 1  # the value THIS call claimed
    return f"EST-{year}-{seq:04d}"
```

- `create()` (§1.1) wraps the sequence bump and the `estimates`/
  `estimate_versions` inserts in **one** `with conn:` block (SQLite's
  Python driver issues `BEGIN`/`COMMIT` around that block already;
  `BEGIN IMMEDIATE` specifically — rather than the driver's default
  deferred `BEGIN` — needs an explicit `conn.execute("BEGIN IMMEDIATE")`
  before the block, since `sqlite3`'s implicit transaction handling
  defaults to deferred. **Verify this empirically against the real
  installed driver behavior during implementation** (rule 12 — don't
  assume `sqlite3`'s isolation-level defaults from memory; the existing
  `_migrate_estimates_table_v2()` procedure already does this explicitly
  outside a transaction for its own reasons, confirm the interaction).
- `%04d` overflow (>9999 estimates in one year) is handled by simply not
  padding beyond 4 digits (`f"{seq:04d}"` naturally prints `10000` at
  seq=10000, just wider than the visual convention) — no special case
  needed, no cap.
- **This is a general-purpose numbering primitive** — if `contract_number`
  ever needs the same treatment (it has the identical client-supplied gap
  today, per §0), the same table/function shape generalizes to
  `contract_number_sequences`. Not built this round (out of scope — one
  thing at a time, rule 1), but logged to `NEW_ISSUES.md` as a `Suspected`
  finding (client-supplied `contract_number` is the same class of gap
  `estimate_number` had) rather than silently left for someone to
  rediscover.

## 3. API routes

Following `routes.py`'s exact hand-rolled `if path == ... / elif method ==
...` style (§0's confirmed convention, `routes.py:1058-1113`). All routes
below sit inside the existing authenticated block (after the `Bearer`/
`?token=` check at `routes.py:492-502`) **except** the `/api/v1/public/
estimate/*` family, which is new and deliberately does **not** reuse either
existing auth mechanism (see §4).

| Method | Path | Calls | Notes |
|---|---|---|---|
| GET | `/api/v1/estimates` | `EstimateService.list()` | query params: `customer_id`, `project_id`, `assigned_to_user_id`, `created_by_user_id`, `workflow_status`, `date_from`, `date_to`, `q`, `limit`, `offset` — same `_parse_int_query_param` helper already used at `routes.py:1061-1067` |
| POST | `/api/v1/estimates` | `EstimateService.create()` | **replaces** `Estimate(**json_body)` (`routes.py:1070`) with explicit field extraction — `customer_id`, `project_id`, `opportunity_id`, `lead_id`, `property_id`, `title`, `terms`, `customer_notes`, `expires_at` pulled individually from `json_body`; anything else in the body is ignored, not merged (§0/§1.1's fix) |
| GET | `/api/v1/estimates/{id}` | `EstimateService.get(include_lines=True)` | replaces the existing GET-by-id block (`routes.py:1074-1079`) |
| PATCH | `/api/v1/estimates/{id}` | `EstimateService.update_header()` | new — this codebase's convention elsewhere uses a `/update` POST suffix (`routes.py:1050`, `update_project`) rather than PATCH; **follow that convention instead** for consistency: `POST /api/v1/estimates/{id}/update` |
| POST | `/api/v1/estimates/{id}/reassign` | `EstimateService.reassign()` | body: `{"assigned_to_user_id": int}` |
| POST | `/api/v1/estimates/{id}/transition` | `EstimateService.transition()` | body: `{"to": "SENT", "comment": "..."}` — this is the one generic endpoint for every actor-driven transition in §1.5's table; the route layer does not special-case `send` vs. `approve` vs. `cancel`, the service's allowed-transitions table is the single source of truth |
| POST | `/api/v1/estimates/{id}/revise` | `EstimateService.revise()` | returns the new version |
| GET | `/api/v1/estimates/{id}/preview` | `EstimateService.preview()` | read-only, server-computed totals for the in-progress draft |
| POST | `/api/v1/estimates/{id}/lines` | `EstimateService.add_line()` | |
| POST | `/api/v1/estimates/{id}/lines/{line_id}/update` | `EstimateService.update_line()` | again following the `/update`-suffix convention, not PATCH |
| POST | `/api/v1/estimates/{id}/lines/{line_id}/delete` | `EstimateService.remove_line()` | POST, not DELETE — no route in this file uses the DELETE HTTP method anywhere (confirmed by grep); matches existing convention rather than introducing one new verb for this one family |
| POST | `/api/v1/estimates/{id}/lines/reorder` | `EstimateService.reorder_lines()` | body: `{"ordered_line_ids": [...]}` |
| POST | `/api/v1/estimates/{id}/convert` | `EstimateService.convert()` | |
| GET | `/api/v1/estimates/{id}/versions` | list versions (thin, no new service concept beyond a query) | for the admin diff view (§6) |
| GET | `/api/v1/estimates/{id}/versions/{n}/diff` | line-by-line diff of two versions | computed in the route/service, not stored — a read-side aggregation over two `estimate_line_items` sets, same "computed, not stored" posture §1.6 already takes for "superseded" |

`/api/v1/portal/estimates` (existing, `routes.py:1372-1376`) is **modified**,
not replaced: it now returns `to_customer_view(...)`'s dict shape per
estimate instead of the raw legacy `Estimate.to_dict()` — this is the actual
fix for F1 the companion plan names (`ARCHITECTURE_PLAN.md:763`). Both this
route and the new public one (§4) go through the exact same
`CustomerEstimateView` allow-list, so there is exactly one code path that
decides what a customer ever sees, not two that could drift.

## 4. Customer share-link delivery — genuinely new, not a reuse of `?token=`

**Explicit statement, since this is the task's own flagged risk**: the
existing `?token=` query-param fallback at `routes.py:497-498` is part of
the *authenticated-session* bearer-token path — a session token obtained
via `/api/v1/auth/login`, just accepted from a query string as well as a
header for convenience. **`estimate_share_links` tokens must never flow
through that code path at all.** They are a different kind of credential
(a capability scoped to exactly one `estimate_version_id`, never a login
session, never resolvable to an `AuthContext`/`actor.user_id`), so they get
their own routing branch, checked **before** the existing
`Authorization`/`?token=` resolution block, not merged into it.

### 4.1 Route family: `/api/v1/public/estimate/{raw_token}/...`

Added to the existing `path.startswith("/api/v1/public/")` block
(`routes.py:465`), which already applies the rate limiter before any auth
check — the new routes inherit that limiter and add a **second, per-token**
bucket on top (a small in-memory or DB-backed counter keyed on
`token_hash`, e.g. 30 requests/hour per token — generous for a customer
reviewing an estimate, tight enough to blunt a token-guessing sweep since
the space is `secrets.token_urlsafe(32)`-sized and effectively unguessable
regardless, defense in depth per §24's own posture).

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/public/estimate/{raw_token}` | Look up `SHA256(raw_token)` in `estimate_share_links.token_hash`. Any of: not found, `revoked_at IS NOT NULL`, `expires_at < now` → **identical 404** `{"error": "Not found"}` for all three cases (§24's "no oracle distinguishing them" requirement, `ARCHITECTURE_PLAN.md:946`) — never a 403 or a different message that would let an attacker distinguish "wrong token" from "expired token" from "revoked token". On success: sets `first_viewed_at` if null, always bumps `last_viewed_at`/`view_count`, triggers the `SENT -> VIEWED` transition (§1.5) if not already past it, and returns `to_customer_view(...)`'s dict. Response headers: `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, `X-Robots-Tag: noindex` (§24, verbatim). |
| POST | `/api/v1/public/estimate/{raw_token}/decision` | Body: `{"decision": "accepted"|"declined"|"changes_requested", "signer_name": "...", "signature_data": "...", "comment": "..."}`. Resolves the token the same way, then calls `EstimateService.record_decision(share_link_id=..., ip=client_ip, user_agent=headers_lower.get("user-agent",""), ...)`. Same 404-for-anything-wrong rule. A second decision against an already-decided version returns `409 {"error": "This estimate has already been responded to"}` — the one case where distinguishing the response IS correct, since the caller already proved they hold the valid token by getting past the lookup. |

### 4.2 Creation — inside `EstimateService`, called by `transition()`'s send step

```python
def _create_share_link(self, estimate_id, version_id, customer_id, actor) -> tuple[EstimateShareLink, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    # ... INSERT estimate_share_links with token_hash only ...
    return link, raw_token   # raw_token returned ONLY to the caller, never persisted
```

- `expires_at` defaults to `now + 30 days` (D10) unless the estimate's own
  `expires_at` is sooner, in which case that wins — an estimate that
  expires in 10 days should not hand out a 30-day-valid link.
- The raw token is embedded once, in the notification email's URL
  (`https://portal.restoricon.com/e/{raw_token}` — the customer-facing host
  routing for `/e/{token}` → this new public API is a deployment/reverse-
  proxy concern, out of this document's scope, same boundary the companion
  plan draws at `ARCHITECTURE_PLAN.md:750`), and is never written to any
  table, log line, or audit record. The audit row for the `send` transition
  records `share_link_id` (the row's `id`, not the token) and
  `delivery_channel`/`delivered_to` (e.g. `"email"`/the customer's email
  address) — enough to know a link was sent and to whom, never enough to
  reconstruct it.
- Revoking a link (`revoke_share_link(link_id, actor)`, `PERM_WRITE_ESTIMATES`
  or the reassign-tier permission) sets `revoked_at`/`revoked_by_user_id` —
  used by `revise()`'s "old links show this estimate has been updated" flow
  (§1.6's cross-reference to `ARCHITECTURE_PLAN.md:760-761`): the OLD
  version's still-valid links aren't deleted, but the GET route above
  checks `estimate_version_id`'s own `is_locked`/`locked_reason='superseded'`
  status (derived, per §1.6) and returns a distinct
  `{"superseded": true, "current_link_url": ...}` body instead of the normal
  estimate view when it detects this — **only if the newer link was issued
  to the same customer**, per the companion plan's own qualifier
  (`ARCHITECTURE_PLAN.md:761`) — i.e., checked via matching `customer_id`
  between the old and current share link rows, not assumed.

## 5. Staff estimator UI — new `/estimates` surface

**New render function `render_estimates_surface()` in `web_surfaces.py`**,
following the `_render_sales_portal()` precedent (`web_surfaces.py:5197`,
its own dedicated function rather than another `_render_staff_portal_base()`
tab) — an estimate builder is exactly the kind of workflow B8's own
precedent already established doesn't fit the generic
schedule-plus-one-list template. Registered in `routes.py` alongside the
existing `/sales`/`/tech`/`/pm` GET routes (`routes.py:440-450` pattern):
`if path in ("/estimates", "/estimates/"): return 200, ..., render_estimates_surface()`.

Reuses, does not reinvent: `_get_common_styles()`, `_get_universal_drawer_html()`,
the `--navy`/`--charcoal`/`--bronze`/`--offwhite` tokens, `.erp-card`/
`.btn-gold`/`.badge-*`, `getAuthToken()`/`Authorization: Bearer`/401-redirect
— every convention `sales_rep_portal.md` §3 already locked in for B8, applied
here without modification.

**Flow (plan §25, `ARCHITECTURE_PLAN.md:958-976`, mobile-first, S24 Ultra
target):**

1. **Customer picker** — a search box (debounced) against the existing
   `AnalyticsSearchService.global_search` or `CRMService.list_customers`,
   not a new search mechanism.
2. **New estimate** — `POST /api/v1/estimates` with the picked
   `customer_id` (and `project_id`/`opportunity_id` if arriving from a
   project/opportunity detail page's "New Estimate" button, matching how
   `sales_rep_portal.md` B8.6 hangs the estimate builder off the customer
   360 view).
3. **Add line sheet** — a bottom sheet (not a separate page — thumb reach on
   a phone), manual entry only this round (no `/pricing/search` — that
   endpoint doesn't exist until the pricing-tables phase lands, per
   `codey_estimator_schema.md` §3's explicit deferral). Fields: description,
   customer description, line type, quantity/unit, unit cost, waste %,
   markup %, and the labor/equipment/sub equivalents, matching
   `estimate_line_items`' input columns 1:1. `inputmode="decimal"` on every
   numeric field, 44px minimum tap targets (§25's explicit numbers).
4. **Review totals** — calls `GET /api/v1/estimates/{id}/preview` after
   every add/edit (debounced), rendering the sticky bottom totals bar from
   the server response only — **the page contains zero arithmetic on money
   fields**, confirmed by a lint-style check during code review (grep the
   new JS for `+`/`*` near a `_cents` variable name, or simpler: a
   code-reviewer manual read, since this file has no JS linter today).
5. **Save** — the line/header mutations already persist as they happen
   (§1.1/§1.8 write on every call); "Save" in the UI is really "return to
   the estimate list," not a separate persistence action — there is no
   draft state that exists only in the browser (draft autosave to
   `localStorage` is explicitly out of scope per §25, "protects against
   accidental navigation only," and even that is optional for v1).
6. **Send** — calls `POST /api/v1/estimates/{id}/transition` with
   `{"to": "SENT"}`, showing the review/internal-review branch's outcome
   (a clear "sent for internal review" vs. "sent to customer" message)
   depending on what the response's resulting `workflow_status` actually
   is — the UI never assumes which branch it took.

**Performance/mobile exit criteria** (matching §25's stated budgets and
`sales_rep_portal.md` B8.13's mobile-QA convention): the page is under
150KB HTML+JS with no framework; single-column layout intact at phone
width; camera/photo-attach (reusing B6.5's existing upload path, if any
line-item evidence photo is attached — likely a B9.x-later nice-to-have,
not required this round) tested on-device, not just in a desktop browser.

## 6. Admin integration — Estimates tab in `render_admin_surface()`

Per plan §17 (`ARCHITECTURE_PLAN.md:713-733`): a new tab in the existing
admin surface (`web_surfaces.py:1672`, following whatever tab-registration
pattern the other domains there already use — read the exact mechanism at
implementation time rather than guessing its shape here, since this
document doesn't reproduce `render_admin_surface()`'s ~3,700 lines).

- **List columns**: number, title, customer, creator, assignee, status,
  version, total — plus **cost/GP/margin, gated behind
  `PERM_READ_ESTIMATE_COSTS`** (rendered server-side conditionally: the
  route's response simply omits those keys for a caller lacking the
  permission, same as the customer-view allow-list does for the public
  route — one enforcement point, the service layer's `list()`/`get()`
  methods from §1.2, not a second client-side hide-the-column check that
  could be bypassed by reading the raw API response).
- **Filters**: `created_by`, `assigned_to`, `customer_id`, `status`,
  `date_from`/`date_to` — all server-side query params against
  `EstimateService.list()`, paginated with `limit`/`offset`, matching plan
  §17's exact filter list.
- **Detail view**: version history (from `GET .../versions`), the diff view
  (`GET .../versions/{n}/diff`), the audit timeline (reusing the **existing**
  `/api/v1/audit-log?entity_type=estimate&entity_id=` route — confirm this
  route already exists and works for other entity types before assuming it
  needs no changes here), share-link status/view count, and decisions.
- **Rule-4/5 note**: this phase touches no schema and no new permission —
  it is UI composition over §1's already-RBAC'd service methods, same
  "wires, does not invent" posture `sales_rep_portal.md` uses throughout §5.
  Still gets a code-reviewer pass (every phase does, per the pipeline), just
  not escalated as its own rule-4 category the way B9.1's schema/RBAC round
  was.

## 7. Quote portal migration (D8) — small, this round's job, not a separate phase

**Resolving the task's own open question**: `Codey-Estimator/docs/DECISIONS.md`
line 17 already answers D8 — *"Remove the public $/sq ft ranges. Replace
with a 'request an estimate' flow"* — recorded 2026-09-27, the same day as
this scoping pass, and stated to be "binding for all implementation phases."
**This is answered, not open**, from the companion library's own
authoritative decision log. What IS still missing is carrying that answer
into `CODEY_MASTER_PLAN.md` §8 the way every other cross-cutting decision on
this project gets logged (per that file's own convention) — this document
does that below, and treats D8 as ready to implement, not as a blocker.

**Scope: small enough to be this round's job, not a separate phase** — it's
a single render-function edit plus zero backend changes:

- `render_quote_surface()` (`web_surfaces.py:713`, the public `/` page)
  currently includes a `$/sq ft` calculator (`.calc-result-box`,
  `.calc-meta-grid` styling at `web_surfaces.py:785-796` confirms a
  calculator UI exists on this page). **Remove the calculator's price-range
  output entirely** — keep the lead-capture form (still posts to the
  existing `POST /api/v1/public/leads`, **unchanged**, since D8 doesn't
  touch lead capture, only the price-expectation-setting calculator), and
  replace the removed calculator section with a plain "Request a Free
  Estimate" CTA that submits the same lead form.
- **No backend/API change** — `submit_public_lead` and its route
  (`routes.py:476-481`) are untouched. This is a pure front-end content
  change, which is why it doesn't need its own phase number: it has no
  schema, no RBAC, no new route, and one exit criterion (the page no longer
  shows a computed price range to an anonymous visitor).
- **Exit criterion**: `render_quote_surface()`'s output contains no
  `calc-result` output tied to a computed dollar figure; the lead form still
  submits successfully to the existing endpoint (regression-tested, not
  just visually confirmed).

## 8. Estimate → Job workflow — `B9.8`

Already specified as `EstimateService.convert()` in §1.9. This is its own
numbered phase (not folded into B9.2) because it's the one method in this
round that writes to **three** existing domains at once (`Contract`,
`Project`, and the `estimates`/`opportunities` link-back) and is exactly the
shape of change rule 4 exists for — a mistake here creates a Project against
the wrong contract or double-creates one. **Rule-4 category.**

- **Depends on**: §1.1-§1.7 (an `ACCEPTED` estimate with a contract already
  created by `record_decision()`), `CRMService.create_project`/
  `get_opportunity` (existing, unmodified).
- **Exit criterion**: a fresh `ACCEPTED` estimate converts to exactly one
  Contract (already existing, from acceptance) and exactly one Project;
  calling `convert()` twice returns the identical `{contract_id,
  project_id}` pair both times (idempotency test, not just a happy-path
  test); an estimate NOT in `ACCEPTED` status is refused with a clear error
  on every other status value (a parametrized test over all ten
  `workflow_status` values, not just one negative case).
- **Depends on Ish's ruling** — see §8... (this document's own §9 below,
  "signed contract required before conversion?").

## 9. Business/policy calls — answered by Ish, 2026-09-27

Same posture B9.1's scoping used for the PM-cost-visibility question. All
five are now resolved and binding on the design below.

1. **Unclaimed-estimate visibility: YES, allow unclaiming.** An "unclaim"
   action (sets `assigned_to_user_id` back to NULL) is in scope for B9.2,
   mirroring `NEW-534`'s claim-workflow pattern for leads/opportunities/
   tasks exactly: an unassigned estimate is visible-and-claimable to any
   `sales`/`sales_manager` actor via the same race-safe conditional
   `UPDATE ... WHERE assigned_to_user_id IS NULL` pattern, not a plain
   read-then-write. `list_estimates`'s ownership narrowing (§1.2) must
   therefore treat "unassigned" as its own visible bucket for `sales`
   actors, not just "mine."
2. **Internal-review mandatoriness: HARD RULE, no per-estimate override.**
   `users.requires_estimate_approval = 1` means that user's estimates
   always require `INTERNAL_REVIEW -> APPROVED_INTERNAL` before `SENT`,
   with no "send anyway" escape hatch for a manager. Simpler state machine,
   no new override permission needed. If a manager disagrees with the
   flag, they turn it off for that user — that's the only override path,
   and it already exists via the flag itself.
3. **Expiry mechanism: A REAL SCHEDULED CHECK, not check-on-read.**
   Overrides this document's own "lazy check" recommendation. **This adds
   new infrastructure that doesn't exist anywhere in Codey-OS today** — no
   cron/scheduler of any kind is currently running in the Core process.
   Design: a new **B9.2b — expiry sweep** sub-task, a single daemon thread
   started/stopped alongside the API server (same lifecycle pattern as the
   B7 backup journal thread — started in `RestoriconAPIServer.start()`,
   joined in `stop()`, PID-safe, **rule-4 category per `CLAUDE.md` rule 4**
   — "the Core API server's binding/auth" and adjacent process-lifecycle
   changes need explicit code-reviewer sign-off regardless of how small).
   Runs on a coarse interval (recommend hourly — expiration is a calendar-
   day-scale event, not sub-minute-sensitive, so this is not the
   `refresh.py`-style token-bucket-rate-limited problem `Codey-Estimator`'s
   pricing layer solves; a plain `time.sleep(3600)` loop is appropriate
   here and should NOT be over-engineered to reuse that library's
   `RefreshPolicy`, which solves a different problem — refresh cadence
   under a paid-API budget, not a one-shot status transition). Each tick:
   `UPDATE estimates SET workflow_status='EXPIRED' WHERE workflow_status
   IN ('SENT','VIEWED') AND expires_at < <now>` (a single, cheap, indexed
   query against `idx_estimates_workflow_status`), each transition
   individually audit-logged (not a bulk silent update — `AuditService.log()`
   per row, matching this project's audit granularity elsewhere). This is
   now its own line item in the phase table below (B9.2b), not folded
   silently into B9.2.
4. **Convert() gate: REQUIRE a signed contract.** More conservative reading
   of plan §22 confirmed. `convert()` must check the linked `Contract`'s
   status is `'signed'` (or `customer_signed_at IS NOT NULL`) before
   creating/linking a `Project` — if no contract exists yet, or it exists
   but isn't signed, `convert()` returns an error directing the estimator
   to obtain a signature first, rather than creating a Project against an
   unsigned contract. This is checkable now, without B8.12's full
   production-handoff checklist existing — B8.12 checks *additional*
   conditions (materials, permits, deposit) on top of this simpler
   "is there a signed contract" gate, and remains a separate future
   phase, not a blocker for B9.8.
5. **`ai_agent`-created estimates: FORCED into internal review**,
   regardless of the assignee's `requires_estimate_approval` flag. A
   structural rule, not per-user configuration: `create_estimate()` sets
   the new estimate's effective review requirement to
   `requires_estimate_approval OR (actor.actor_type == "agent")` at
   creation time (stored as a flag on the estimate itself, e.g. an
   `internal_review_required` snapshot column — see the schema note below
   — not re-derived from the creator's *current* user flag on every read,
   since the creator could change roles or the flag could be edited later;
   the decision must be pinned at creation, same reasoning as
   `created_by_name` being a snapshot). **Schema note, deferred to B9.2's
   own migration, not re-opening B9.1**: this needs one more additive
   column, `estimates.internal_review_required INTEGER NOT NULL DEFAULT 0
   CHECK(... IN (0,1))`, computed once at creation and never recomputed —
   B9.1's schema doc predates this decision (D5 only anticipated the
   per-user flag, not a per-estimate pinned snapshot of it), so this is a
   small, additive, non-controversial follow-on to B9.1's migration, done
   as part of B9.2's own scope rather than reopening the already-reviewed
   B9.1 branch.

## 10. Cross-reference — what this round explicitly does NOT do

Mirroring `sales_rep_portal.md` §7's convention:

- Does not build any pricing table (`retailer_products`, `price_book_items`,
  `labor_rates`, …) or the `/pricing/search` endpoint — deferred phase,
  unchanged from `codey_estimator_schema.md` §3's scope decision. The staff
  UI (§5) is manual-entry-only this round as a direct consequence.
- Does not build `properties` (B8.1) — `property_id` stays a bare,
  unenforced int on `estimates` until that table exists, per B9.1's own
  note.
- Does not build the B8.12 production-handoff checklist or its
  contract-signed-plus-deposit gate — §1.9/§8 item 4 flags the resulting
  gap in `convert()` rather than building B8.12 as a side effect of this
  round.
- Does not add push/real-time notification for "estimate viewed" events —
  poll-on-load, consistent with D3's resolution in `sales_rep_portal.md`
  §4a item 3 (12-second refresh where live-ness matters at all; an
  estimate-viewed notification is not latency-sensitive enough to need
  even that).
- Does not touch `appointments`, Aigentik internals, or CCOS memory — same
  boundaries `sales_rep_portal.md` §6 already states, unchanged for this
  domain.
- Does not migrate `contract_number` to the new numbering primitive (§2) —
  logged as a `NEW_ISSUES.md` finding, not silently fixed alongside
  `estimate_number`.

## 11. Phase summary (for `CODEY_MASTER_PLAN.md` §6.13/Appendix A)

| Phase | Delivers | Rule-4/5/7 category | Blocked on |
|---|---|---|---|
| **B9.2** | `EstimateService` (new file): create/get/list with real ownership narrowing (incl. an unassigned/unclaimed bucket, per §9 item 1) + D9 cost gating, update_header, reassign, atomic `claim`/`unclaim` (NEW-534-style race-safe conditional UPDATE), the full workflow state machine (hard internal-review gate, no override, per §9 item 2; `ai_agent`-originated estimates forced into review via a pinned `internal_review_required` snapshot column, per §9 item 5 — a small additive migration on top of B9.1, not a B9.1 reopen), versioning/revise, decision recording, line-item CRUD with server-authoritative `calculate()` integration, race-safe `estimate_number` generator | **Rule-4** (money, workflow, RBAC narrowing, schema addition) | B9.1 merged to `main`, live-verified |
| **B9.2b** | Expiry sweep: a single daemon thread in the API server process (started/stopped with `RestoriconAPIServer`, same lifecycle discipline as the B7 backup thread), hourly, transitioning `SENT`/`VIEWED` estimates past `expires_at` to `EXPIRED`, each transition individually audit-logged. **New infrastructure — no scheduler of any kind exists in Codey-OS today.** Per §9 item 3 (Ish overrode this document's own "check on read" recommendation) | **Rule-4** (process lifecycle — `CLAUDE.md` rule 4 explicitly names this category) | B9.2 |
| **B9.3** | API routes: `/api/v1/estimates/...` full set per §3's table, `/api/v1/portal/estimates` fixed to the allow-list serializer | Rule-4 (auth-boundary-adjacent — narrows what an existing route returns) | B9.2 |
| **B9.4** | Public share-link delivery: `estimate_share_links` creation/lookup, `/api/v1/public/estimate/{token}/...` (path-token, never `?token=`), decision recording, `NotificationService` wiring for send + confirmation emails | **Rule-4** (new customer-facing auth boundary — §3.5's plan-§3 "auth boundary" risk category) | B9.2, B9.3 |
| **B9.5** | Staff `/estimates` mobile-first surface: customer picker → new estimate → add-line sheet → server-computed preview → send | Rule-5/7 (UI wiring over already-RBAC'd services; no new schema/permission) | B9.3 |
| **B9.6** | Admin `Estimates` tab: list/filter/detail/diff/audit-timeline, cost columns gated by `PERM_READ_ESTIMATE_COSTS` | Rule-5/7 | B9.3 |
| **B9.7** | Quote portal migration (D8): remove the public $/sq-ft calculator from `render_quote_surface()`, replace with a request-an-estimate CTA | Rule-5/7 (front-end only, no schema/API change) | none (independent of B9.2-B9.6, can ship any time) |
| **B9.8** | Estimate → Job workflow: `convert()`'s Project-creation half, gated on a signed Contract (per §9 item 4 — Ish chose the more conservative reading), idempotency, linkage to existing Opportunity/Project | **Rule-4** (writes across three domains at once) | B9.2 |
| **B9.x** (existing, unchanged) | Pricing/retailer tables | Rule-4 | `codey_estimator.ports.py` binding work, unaffected by this document |

---

## Appendix: forbidden-keys / customer-isolation test obligations (rule from `CLAUDE.md`, this repo's own copy of the estimator library's rule)

Per `Codey-Estimator/CLAUDE.md`'s constraint ("Customer-visible data only
ever passes through an allow-list serializer... Every DTO change needs the
forbidden-keys test updated") — carried into this integration:

- A unit test serializing a fully-populated `EstimateHeader` +
  `EstimateVersion` + several `EstimateLineItem`s (including cost, markup,
  waste, retailer/SKU/observation ids, internal notes, and a
  `price_override_reason`) through `to_customer_view()` and asserting the
  forbidden-key set (`cost_total_cents`, `gross_profit_cents`,
  `gross_margin_bp`, `material_cost_cents`, `unit_cost_cents`,
  `retailer_code_snapshot`, `internal_note`, `override_reason`,
  `created_by_user_id`, every `*_rate_cents` column) is **absent** from
  the result — this test already exists in the `Codey-Estimator` library
  itself; **B9.3's exit criterion is confirming it still passes unchanged
  when exercised through the Core's own `/api/v1/public/estimate/{token}`
  and `/api/v1/portal/estimates` routes**, not re-writing it.
- Both customer-facing routes (public share-link and authenticated portal)
  must be proven, by test, to call the **same** `to_customer_view()`
  function — not two independently-written serializers that could drift.
