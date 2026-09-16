# Restoricon Sales Rep Portal — Build Plan

**Status: PLAN ONLY, nothing in this document is built.** Written
2026-09-16. This is a spoke, not a second hub — `CODEY_MASTER_PLAN.md`
remains the single authoritative plan (per its own front matter and
`CLAUDE.md` rule "start here"). This document is registered there as
**Phase B8** (§6, Appendix A) with a one-line pointer back to this file;
do not let the two documents' status claims drift apart. Field lists
already defined in `CODEY_MASTER_PLAN.md` Appendix C are **not repeated
here** — this document only enumerates fields for genuinely net-new
tables that Appendix C does not cover (Property, Commission, Insurance
Claim, Financing, Territory, Assessment, Package Option, Production
Handoff, Referral).

## 0. The one rule this whole plan exists to enforce

> "The portal should expose capabilities from Codey-OS, not create a
> second disconnected business brain." — Ish, framing this task.

Concretely, in terms of what already exists in this repo:

- **The system of record is `restoricon_core`** (`/data/data/com.termux/files/home/Codey-OS/restoricon_core/`) —
  one SQLite-backed Core, one `DatabaseManager`, one set of services
  (`CRMService`, `FinanceService`, `SchedulingService`,
  `OperationsService`, `AutomationService`, `AnalyticsSearchService`,
  `CommunicationService`, `AuditService`, `NotificationService`,
  `BusinessOpsService`), one API (`api/routes.py` behind
  `api/server.py`), one auth/permission system (`auth.py`).
- **The portal is a rendering layer over that API**, in
  `api/web_surfaces.py` — server-rendered HTML + vanilla JS `fetch()`
  calls against `/api/v1/*`, no separate frontend build, no client-side
  data store. §6.9 decision 8 (`CODEY_MASTER_PLAN.md:3979`) already
  commits every web surface to **refetch from the one API on load and
  after every action, holding no local copy.** Every phase below
  inherits that constraint without restating it.
- **Every new capability this plan adds is a new service method, a new
  API route, and a new rendered surface over the existing Core** — never
  a new database, never a parallel copy of customer/lead/project data,
  never a store inside Aigentik or the static website.

This plan is therefore a *build-out and wiring plan*, not a from-scratch
CRM design. §1 states the honest current baseline; §2 states the real
gaps; everything after that is phases closing those gaps.

## 1. What already exists — read, not assumed

Verified 2026-09-16 by reading the files directly (`CLAUDE.md` rule 12).

### 1.1 The existing "sales rep portal"

`render_sales_surface()` (`api/web_surfaces.py:5036`) calls
`_render_staff_portal_base("Sales & Estimating", "My Active
Opportunities", "sales")` (`api/web_surfaces.py:4894-5031`) — the same
template shared by the PM, technician, and subcontractor portals
(B6.8, done 2026-09-06 per `CODEY_MASTER_PLAN.md:6666`). As it stands
today it renders exactly two panels:

- **"My Schedule"** — fetches `/api/v1/staff-schedules?user_id=<id>`.
- **"My Active Opportunities"** (labelled generically per-role) —
  fetches `/api/v1/projects` and, for `role_key == 'sales'`, applies
  **no client-side filter at all** (the filter branch only handles
  `project_manager`, `technician`, `subcontractor` —
  `web_surfaces.py:4998-5010`). This is a real, currently-shipped gap:
  a sales rep's portal today shows the same `/api/v1/projects` list
  everyone else's does, unfiltered to their own leads/opportunities.
  **Log this as `NEW-###` in `NEW_ISSUES.md` before B8.2 starts** (rule
  8 — found outside this task's scope, not silently fixed here).

Visual language it inherits from `_get_common_styles()` /
`_get_universal_drawer_html()`: `--navy: #0A192F`, `--charcoal:
#1E293B`, `--bronze: #D4AF37`, `--offwhite: #F8FAFC` (also defined in
the public site's `restoricon/style.css:5-9`, confirming portal and
website already share the token names), header-card gradient
`linear-gradient(135deg, #112240 0%, #1c2e4a 100%)`, `.btn-gold`,
`.badge-*` classes, and the slide-out drawer nav. **§3 below is this
plan's visual spec — it extends these exact tokens, it does not invent
new ones.**

Login: `/admin/login` for all staff, role-based redirect to
`/admin`/`/pm`/`/sales`/`/tech`/`/subcontractor` (B6.8, "Smart Login
Routing", `CODEY_MASTER_PLAN.md:4224-4227`) — already built, reused
as-is.

### 1.2 Core services the sales portal must wire to, not rebuild

From `restoricon_core/services/crm_service.py` (4,105 lines) — already
implemented and unit-tested:

| Capability this plan needs | Existing method |
|---|---|
| Lead capture (manual + public web form) | `create_lead`, `submit_public_lead` |
| Lead scoring | `score_lead` |
| Lead → pipeline | `create_opportunity`, `transition_opportunity_stage` |
| Pipeline summary / forecast | `get_pipeline_summary` |
| Follow-up automation seeding | `generate_cadence_tasks` |
| Task CRUD | `create_task` / `update_task` / `complete_task` |
| Customer 360 | `get_customer`, `list_customers`, `update_customer` |
| Multi-project-per-customer | `list_projects(customer_id=...)` |
| Estimates | `create_estimate`, `list_estimates` |
| Contracts + e-signature | `create_contract`, `sign_contract` (fails closed — `NEW-272` note, `CODEY_MASTER_PLAN.md:3939-3942`) |
| Invoices / deposits | `create_invoice`, `record_payment` |
| Documents | `create_document`, `list_documents` |
| Communication log | `CommunicationRecord`, logged via `communication_service.py` |
| Public booking (website → appointment) | `submit_public_booking` |
| Global search | `AnalyticsSearchService.global_search` (Appendix C item 19 — already exists, wire the UI, do not rebuild) |
| Executive/rollup metrics | `AnalyticsSearchService.get_executive_dashboard` (already exists — B8.2 wires this, it is not new backend work) |
| Workflow rules | `AutomationService` / `AutomationRule` — **rule-matching on record state, not an event bus.** Confirmed by reading `api/server.py:78-92`: `_dispatch` is HTTP method routing only, there is no `emit`/`publish`/`on_event` anywhere in `restoricon_core`. Any "event-driven" language in this plan (§7-ish equivalents) means *extending `AutomationRule` matching*, not adding a message bus — stated explicitly so a later reader doesn't assume infrastructure that isn't there. |
| Staff scheduling | `SchedulingService` + `StaffSchedule` table (B6.7) — **`appointments` itself is Aigentik's live `calendar.js` write-through target with `external_id` idempotency and must not be schema-changed**; this is why B6.7 added a sibling table instead of touching `appointments`, and every phase below that needs new appointment-adjacent fields follows the same rule. |
| Permissions | `auth.py` — `ROLE_SALES` exists; `ROLE_ADMIN`, `ROLE_MANAGER`, `ROLE_PROJECT_MANAGER`, `ROLE_TECHNICIAN`, `ROLE_AI_AGENT`, `ROLE_CUSTOMER` are the only other roles. **There is no `sales_manager` role today** — see Open Decision D2 below. |

Nothing above gets rebuilt. Every phase in §5 either (a) adds a UI
panel that calls an existing method, or (b) adds the smallest possible
service/schema delta where a capability genuinely does not exist yet.

## 2. Gap analysis — what's genuinely missing

Checked by grep across `restoricon_core` for each concept; absence
confirmed, not assumed.

| Concept the request needs | Status |
|---|---|
| Commission ledger | **Missing entirely.** No `Commission` class in `models.py`, no commission logic in `finance_service.py`. Net-new. |
| Property (as distinct from Customer/Project) | **Missing.** Addresses live inline on `Customer` and `Project`; nothing represents "a customer owns 3 properties, each with its own history." Net-new. |
| Insurance claim tracking | **Missing.** `Customer`/`Project` have no claim fields. Net-new. |
| Financing tracking | **Missing.** Net-new. |
| Territory / ZIP assignment | **Missing.** Net-new (small — a field plus a lookup, not a subsystem). |
| Assessment / inspection checklist + evidence | **Missing** as a structured record. `Document` supports photo/file attachment generically but nothing models a checklist-by-area inspection. Net-new, but built *on* `Document`/B6.5's file store, not a parallel one. |
| Good/Better/Best package options | **Missing** as a mechanism. `Estimate` has line items but no tiered-option grouping. Net-new, small. |
| Production handoff checklist | **Missing** as a gated step. `Project` creation exists; nothing currently blocks "production" work from starting before contract+deposit conditions are met. Net-new — a checklist table plus one guard condition, not a new module. |
| Referral tracking | **Partially exists** — `lead_source` on `Lead`/`Customer` already carries a source string; `MarketingCampaign` exists for campaign tracking. What's missing is *referral compensation*, which folds into the new Commission ledger (a `commission_type='referral'` row), not a new table. |
| AI Sales Copilot | **Missing**, and deliberately last — depends on CCOS (`ccos/`), which is a separate, mid-build layer (`CODEY_MASTER_PLAN.md` §3.2). Do not front-load this. |
| Real-time push notifications | **Missing, and out of scope by prior decision** — see Open Decision D3. |
| Website homepage packages | **Exist and are the ground truth** — `restoricon/home-care.html` defines **HomeCare Basic / Plus / Complete / Estate** (four membership tiers). The request's generic "Essential/Enhanced/Premium" language does not match the real product; this plan uses the real names and treats Good/Better/Best as a *separate* mechanism for remodeling scope options, not a renaming of the HomeCare tiers. |

## 3. Design system — reuse, don't invent

Source of truth: `restoricon/style.css` and `_get_common_styles()` /
`_get_universal_drawer_html()` in `api/web_surfaces.py`. New sales-portal
screens must:

- Use the existing CSS custom properties (`--navy`, `--charcoal`,
  `--bronze`, `--offwhite`) and the existing dark-mode override block
  (`style.css:3316-3318`) rather than hardcoding colors.
- Reuse `.erp-card`, `.header-card`, `.btn-gold`, `.badge-*`,
  `table`/`th`/`td` styles already defined for the staff-portal base —
  new panels are additional `.erp-card` blocks in the same
  `.portal-layout` column, not a new layout system.
- Reuse the universal slide-out drawer (`_get_universal_drawer_html`)
  for navigation rather than building a second nav pattern.
- Follow the existing `getAuthToken()` / `fetch(..., {{headers:
  {{Authorization: 'Bearer '+token}}}})` / `res.status === 401 →
  redirect` pattern verbatim — it is already the convention across
  every staff and customer surface.
- Mobile-first is enforced by keeping the existing single-column
  `.portal-layout` flex behavior and large tap targets; do not introduce
  a desktop-only grid that has to be retrofitted for phone use (§32 of
  the request maps directly onto "don't regress this").

## 4. Open decisions needed from Ish before certain phases can start — ANSWERED 2026-09-16

All five answered by Ish this session. Recorded here verbatim in
substance, and in `CODEY_MASTER_PLAN.md` §8 per that file's own
convention for open decisions. **Two of the five answers change this
plan's B8.1 design from what already shipped** (see the `NEW-533` fix,
`NEW_ISSUES.md`) — flagged explicitly below rather than silently
treated as still-current.

- **D1 (SMS) — Email only for now.** Communications Center (§14 of the
  original request, Phase B8.10) scopes to email + the existing logged
  communication history. SMS stays out until Aigentik's SMS path is
  real (B6.9 decision 9 still stands, unchanged).
- **D2 (sales-manager tier) — Ish chose the schema option, overriding
  this plan's original recommendation and the design that already
  shipped in the `NEW-533` fix.** The `NEW-533` round built a
  **permission-grant model** (`PERM_READ_TEAM_SALES_DATA` on the
  existing `sales` role, no schema change) because it was the smaller,
  faster, already-proven-pattern option — but Ish's answer here is
  **add a real `sales_manager` role** (a new value in the `users.role`
  CHECK constraint), so "sales manager" is visible everywhere as its
  own role (user lists, reports, filters) rather than an invisible
  permission flag on a `sales` user. **This is now its own follow-on
  task, not yet built**: migrate the shipped permission-grant
  mechanism to a real role. Rule-4 category (schema + RBAC) — needs
  its own `project-architect` → `implementer` → `code-reviewer` round.
  Open design question for that round: does `sales_manager` keep
  `PERM_READ_TEAM_SALES_DATA` as how the narrowing logic recognizes it
  (role implies the permission, narrowing code stays permission-keyed
  and unchanged), or does narrowing switch to checking role directly
  (would reopen the role-vs-permission-keyed question the
  `PERM_REASSIGN_PROJECT_STAFF` precedent exists to avoid — recommend
  the former: keep narrowing permission-keyed, just also grant
  `PERM_READ_TEAM_SALES_DATA` by role default to the new
  `sales_manager` role, exactly like `admin`/`manager`/`ai_agent`
  already work).
- **D3 (real-time push) — Ish chose to add a real-time push layer,
  overriding B6.9 decision 8** ("no realtime push layer — not needed,
  not built," `CODEY_MASTER_PLAN.md:3979`, previously a standing
  cross-cutting constraint on every web surface, not just sales).
  **This is a genuinely large, cross-cutting infrastructure build**,
  not a sales-portal-scoped task — it changes §6.9 decision 8 for the
  whole system, since a push layer built only for `/sales` while every
  other surface stays poll-only would be an inconsistent, hard-to-reason-about
  architecture. Recommend this becomes its own dedicated phase (not a
  `sales_rep_portal.md` sub-item) with its own `project-architect`
  scoping pass covering: transport choice (WebSocket vs. SSE vs.
  polling-interval reduction as a cheaper middle ground), which events
  actually need to be real-time (new-lead alert is the concrete case
  in the original request) vs. which can stay poll-on-load, and how it
  interacts with §3.5's one-API/no-local-store design. **Not scoped
  further in this document** — flagged as a new, larger initiative.
- **D4 (commission plan) — real numbers provided**, from
  `Sales_Rep_Contract.docx` (Ish's own Downloads folder, read directly
  2026-09-16, not guessed at). This replaces B8.7's placeholder design
  with the actual plan:
  - **Phase 1 — flat commission at assessment sale.** $100 flat per
    $299 Initial Property Assessment sold, booked, and paid.
  - **Phase 2 — subscription upsell bonus, one-time at upgrade,** paid
    when the homeowner upgrades to a recurring HomeCare tier following
    the assessment: bonus = first month's subscription fee minus the
    $100 already paid in Phase 1. Confirms the real four-tier pricing
    (matches `home-care.html`'s Basic/Plus/Complete/Estate naming from
    §2's ground-truth note): Basic $179/mo → $79 bonus; Plus $399/mo →
    $299 bonus; Complete $599/mo → $499 bonus; Estate $999+/mo → $899+
    bonus (tier price variable/negotiated at the top end, per the
    contract's own "$899+" phrasing).
  - **Phase 3 — portfolio override, residual, 5%,** on gross collected
    revenue of any major general-contracting project (roofing, siding,
    storm damage repair, flood restoration, etc.) generated from a
    HomeCare account the rep originally originated — for **12 months
    from origination ("life of the contract")**, not 12 months from
    the override payout. This is the "referral" `source_type` this
    plan's §2 gap analysis anticipated, but it's really its own
    distinct commission type (residual override on a *portfolio* the
    rep built, not a one-time referral bonus) — **`B8.1`'s
    `CommissionLedgerEntry.source_type` enum should be `assessment` /
    `subscription_upsell` / `portfolio_override` / `bonus` /
    `adjustment` / `chargeback`**, not the original placeholder list.
  - **Clawback rule, concrete:** Phase 2 bonuses carry a **90-day
    retention period** — if the homeowner cancels their HomeCare
    subscription within 90 days of enrollment, 100% of that Phase 2
    bonus is clawed back, deducted from the rep's future commission
    payments. This is a real, dated trigger condition
    `CommissionLedgerEntry`'s `chargeback` rows need to key off (an
    automation check at day 90, or triggered directly off a
    subscription-cancellation event/status change).
  - **Termination rule:** unpaid Phase 1/Phase 2 commissions already
    earned before a rep's termination date remain payable. **Phase 3
    portfolio overrides cease permanently upon termination** — no
    residual override accrues on projects sold after the rep's
    contract with Restoricon ends, even against accounts they
    originally built.
  - This is now the authoritative source for B8.7's schema/logic —
    supersedes §2's and Phase B8.7's original generic placeholder
    language. `sales_rep_portal.md` is a spoke, so this real-numbers
    summary lives here (not duplicated into `CODEY_MASTER_PLAN.md`
    Appendix C, which doesn't own commission-plan detail).
- **D5 (financing) — manual tracking only, confirmed.** No integration
  work; `FinancingRecord` (B8.8) stays data-entry-only until/unless a
  real provider is chosen.

### NEW-534 priority — ANSWERED: prioritize a fix now

Ish chose to prioritize `NEW-534` (`NEW_ISSUES.md`) rather than defer
it to Phase B8.3. Not yet built. Scope for that round: an explicit
"claim this lead/opportunity/task" action with race protection (a
conditional `UPDATE ... WHERE assigned_user_id IS NULL`, returning a
clean "already claimed" response on a losing race rather than a silent
overwrite), replacing the current unclaimed-pool-is-visible-and-freely-editable
state the `NEW-533` fix shipped as a stopgap. Rule-4 category
(mutates assignment, same family as B6.1's reassignment permission
work) — needs its own scoping round.

## 4a. Follow-on work queue from this session — not yet built

Recorded here so the next round doesn't have to reconstruct it from
chat history. Three separate tasks, each needing its own
`project-architect` → `implementer` → `code-reviewer` pipeline pass:

1. ~~**D2 — migrate the sales-manager permission grant to a real
   `sales_manager` role.**~~ **DONE 2026-09-16 — code-complete,
   code-reviewer APPROVED, LIVE-VERIFIED against the real production
   DB.** Full detail in `CODEY_MASTER_PLAN.md`'s Appendix A `B8.1a`
   entry and `NEW_ISSUES.md`'s `NEW-538`/`539`/`540`/`541` (spun-off
   findings, none fixed, all logged). The `PERM_READ_TEAM_SALES_DATA`
   custom-permission grant mechanism from the `NEW-533` fix still
   works exactly as before — this added a role that has it by default,
   it did not remove the general-purpose override.
2. ~~**NEW-534 — claim workflow with race protection** for unassigned
   leads/opportunities/tasks.~~ **DONE 2026-09-16 — code-complete,
   code-reviewer APPROVED.** Full detail in `CODEY_MASTER_PLAN.md`'s
   Appendix A `NEW-534` entry and `NEW_ISSUES.md`. Spun off `NEW-542`
   (the generic update path's own pre-existing race on the same
   column, not fixed, deliberately out of scope).
3. **D3 — real-time push layer.** Largest and most architecturally
   significant; recommend its own dedicated scoping session rather
   than folding into a B8 sub-phase, since it changes a system-wide
   standing design decision (B6.9 decision 8), not just sales.
   **Scoping pass done 2026-09-16, design only, nothing built:**
   `docs/realtime_push_design.md`. Needs Ish's direct review before an
   `implementer` round is scoped from it (architecture-reversal
   stakes). See `PROJECT_LOG.md` 2026-09-16 entry for the summary.

## 4b. Original open decisions needed from Ish before certain phases can start

Per `CLAUDE.md`: don't contradict a logged decision without an explicit
new one from Ish. Several things in the original request collide with
decisions already on record in `CODEY_MASTER_PLAN.md` §6.9. Flagging
rather than silently building around them.

- **D1 — SMS in the Communication Center (§14 of the request).**
  B6.9 decision 9 (`CODEY_MASTER_PLAN.md:3980`): *"Email now; SMS is an
  investigation item, not a deliverable."* The request's Communication
  Center assumes SMS is live. **Needs Ish's sign-off** before B8.10
  (Communications) can treat SMS as more than a read-only log of
  whatever Aigentik already sends.
- **D2 — Is there a `sales_manager` tier?** The request describes
  manager-level pipeline/team visibility (§19, §26, §33). Today there is
  only `ROLE_SALES` — no manager role for sales specifically (`ROLE_MANAGER`
  is company-wide). Two ways to build it: (a) a new CHECK-constraint role
  value (schema migration, rule-4 category), or (b) a scoped permission
  like `PERM_READ_TEAM_PIPELINE` granted to specific `sales` users via
  the existing per-user `custom_permissions_json` override — the same
  additive-permission pattern as `PERM_REASSIGN_PROJECT_STAFF` /
  `PERM_REASSIGN_ANY_PROJECT_STAFF` (B6.1 precedent). **This plan
  recommends (b)** — no schema/role-table change, reuses the
  already-proven pattern. Needs Ish's confirmation before B8.2/B8.7 build
  manager-tier views.
- **D3 — Real-time notifications (§31, §37's "CODEY RECOMMENDS" live
  ticker).** B6.9 decision 8 (`CODEY_MASTER_PLAN.md:3979`) states
  explicitly: *"No realtime push layer — not needed, not built."* Every
  "notification" in this plan is therefore **poll-on-load / poll-on-action
  against the API**, exactly like every other surface, not a websocket
  or push channel. If Ish wants that changed, it's a new decision, not
  something this plan can assume.
- **D4 — Commission plan structure.** The request names several
  commission bases (flat %, subscription residual, tiered bonus,
  chargebacks). Before B8.7's schema is finalized, need Ish's actual
  compensation-plan rules (percentages, whether HomeCare subscription
  commission is one-time or residual, chargeback window) — this plan
  builds the *mechanism* (an append-only ledger with a pluggable
  `commission_rule` reference), not the specific numbers.
- **D5 — Financing provider.** No financing integration exists anywhere
  in the repo. Needs Ish to name whether Restoricon has a financing
  partner today (e.g., a specific POS/financing API) or whether this
  phase is manual tracking only until one is chosen.

## 5. Phase plan

Each phase states: what it delivers, what existing code it wires to,
what schema (if any) it adds, its rule-4/5/7 category, and its exit
criterion. Phases are ordered by dependency, then risk, then value —
same method B6.9 used. **Nothing below is marked done; this is the
target state only.**

Numbering: this is **Phase B8** in `CODEY_MASTER_PLAN.md` §6, following
B7 (backup/DR). It has its own sub-numbering `B8.1`…`B8.14` for the
same reason B6 did — it is the largest phase in this plan.

---

### B8.1 — Foundation schema: Property, Commission ledger, sales-manager permission

**Rule-4 category** (new tables touching money and RBAC). Prerequisite
for almost everything else, so it leads.

- **`Property`** table (net-new). Fields: `id`, `customer_id` (FK,
  nullable — a property can exist before a customer record if sourced
  from an assessment), `address`, `parcel_number`, `property_type`,
  `year_built`, `square_footage`, `stories`, `roof_type`,
  `exterior_type`, `existing_systems_json`, `insurance_carrier`,
  `notes`, `created_at`, `external_id` (matches the `external_id`
  idempotency convention used on `Lead`/`Appointment`/`Subcontractor`).
  `Project` gains an optional `property_id` FK (nullable, additive —
  does not replace `Project.address`, avoids a breaking migration).
- **`CommissionLedgerEntry`** table (net-new), **append-only by
  convention** — no UPDATE of an existing row, only new rows
  (correction/chargeback/adjustment are their own rows referencing the
  original via `reversed_entry_id`), mirroring the audit-ledger
  discipline `AuditRecord` already uses. Fields: `id`, `rep_user_id`,
  `source_type` (`assessment` | `subscription` | `remodel` |
  `referral` | `bonus` | `adjustment` | `chargeback`), `source_id`
  (polymorphic ref to `Invoice`/`Project`/`Contract`), `basis_amount`,
  `commission_rate_or_flat`, `commission_amount`, `status`
  (`pending` | `earned` | `paid` | `reversed`), `earned_at`, `paid_at`,
  `reversed_entry_id` (nullable), `created_by`, `notes`.
- New permission `PERM_READ_TEAM_PIPELINE` / `PERM_READ_TEAM_COMMISSIONS`
  per Open Decision D2 — additive, per-user override via
  `custom_permissions_json`, following the `PERM_REASSIGN_*` precedent
  exactly. **Blocked on D2 confirmation.**
- **Exit criterion:** migration applies cleanly against the live
  `~/.codeyOS/restoricon.db` schema (not a fresh test DB — B7.1's
  rule-6 correction is the standing reminder of why that distinction
  matters), `CRMService`/`FinanceService` unit tests cover
  create/read/reverse for both new tables, code-reviewer approves
  (rule-4).

### B8.2 — Command Center dashboard (request §1, §37)

Wires, does not invent: `get_executive_dashboard`, `global_search`,
`get_pipeline_summary`, `list_tasks`. Also fixes the currently-real gap
noted in §1.1 (sales portal shows unfiltered `/api/v1/projects`).

- New `/api/v1/sales/dashboard` route aggregating: today's/upcoming
  appointments (from `staff_schedules` + `appointments` filtered to the
  rep), new/uncontacted leads (`list_leads(status=...)`), follow-ups
  due/overdue (`list_tasks` filtered by due date), quotes/estimates/
  contracts awaiting action (existing list methods filtered by status),
  pipeline value (`get_pipeline_summary`), and the rep's own commission
  totals from B8.1's ledger.
- Manager-tier variant of the same route gated behind
  `PERM_READ_TEAM_PIPELINE` (D2), reusing `get_executive_dashboard` for
  the company-wide numbers.
- **No live ticker** — per D3, this is populated on page load and on an
  explicit refresh action, not a push feed.
- **Exit criterion:** one API call renders the full command-center view
  with real data from a seeded dev DB; rep sees only their own data,
  verified by a test asserting a second rep's data is absent from the
  response, not just filtered client-side.

### B8.3 — Lead & pipeline UX (request §2, §3)

Wires `create_lead`, `score_lead`, `list_leads`, `update_lead`,
`create_opportunity`, `transition_opportunity_stage`,
`generate_cadence_tasks`.

- Lead list + detail view, pipeline kanban view driven by
  `PipelineStage`/`transition_opportunity_stage` (the stage list
  Appendix C item 3 already defines — reuse verbatim, do not invent a
  different stage set for this portal).
- "Where leads get stuck" analytics: a small addition to
  `AnalyticsSearchService` — average time-in-stage per `PipelineStage`,
  computed from the existing stage-transition audit trail (every
  `transition_opportunity_stage` call already logs via `AuditService`
  per B6.2's standard — this is a read-side aggregation, not new
  write-path work).
- **Exit criterion:** a rep can take a lead from creation through every
  pipeline stage using only this UI, each transition audit-logged with
  old/new stage per the B6.2 standard.

### B8.4 — Customer 360 & multi-property records (request §4, §5)

- Customer detail view aggregating existing per-customer lists:
  projects, estimates, contracts, invoices, documents, communications,
  appointments, tasks — all already listable by `customer_id`/similar
  FK through existing service methods; this phase is UI composition,
  not new backend surface, **except** the new `Property` list per
  customer from B8.1.
- Property detail view: history, insurance info, project history,
  document/photo list scoped to `property_id`.
- **Exit criterion:** opening one customer shows every record type the
  request lists in §4, each sourced from its existing service method,
  with no duplicated/cached copy of any field.

### B8.5 — Appointments & property assessment (request §6, §7)

- Appointment creation/detail UI wired to `SchedulingService` +
  `AppointmentType` (already supports the type catalog, concurrency cap
  — B6.7/B6.9 phase 4). **Does not modify `appointments`' schema** — any
  new per-appointment sales-specific field (required documents,
  talking points) goes on a new sibling table keyed by
  `appointment_id`, same reasoning as `staff_schedules`.
- **`AssessmentRecord`** table (net-new): `id`, `appointment_id`,
  `property_id`, `checklist_json` (area → findings, matching the
  request's exterior/interior/roof/... checklist), `evidence_document_ids_json`
  (references into the existing `Document`/B6.5 file store — photos and
  voice notes are just `Document` rows with `category='assessment'`, not
  a new storage mechanism), `customer_statements`, `created_by`,
  `created_at`.
- Camera capture flow: reuses B6.5's existing 25MB-cap local-disk
  upload path (`CODEY_MASTER_PLAN.md:3976`), no new storage layer.
- **Exit criterion:** a rep can complete an assessment checklist,
  attach photos taken in-app, and the record is retrievable from both
  the appointment and the property.

### B8.6 — Estimates, packages, proposals, contracts (request §9, §10, §11, §12)

- Estimate builder UI wired to `create_estimate`/`list_estimates`.
- **`PackageOption`** table (net-new, small): `id`, `estimate_id`,
  `tier` (`good`|`better`|`best`, project-scoped — **distinct from and
  never mixed with** the website's HomeCare Basic/Plus/Complete/Estate
  membership tiers per §2's ground-truth note), `price`,
  `gross_profit`, `margin`, `included_items_json`. Portal computes
  margin/commission preview per tier client-side from server-returned
  numbers, never invents pricing logic duplicated from `FinanceService`.
- Proposal builder: server-rendered PDF/HTML from existing `Estimate` +
  `Contract` + `BusinessProfile` (license/insurance info already
  modeled) data — a template, not new business data.
- Contract flow wired to existing `create_contract`/`sign_contract`
  (already fails closed — reuse as-is).
- **Exit criterion:** generate → send → track → sign works end to end
  against a real (dev) contract record, package tiers computed
  server-side and shown identically in the estimate and the generated
  proposal.

### B8.7 — Commission engine & compensation dashboards (request §18, §19)

**Rule-4 category** (money). Blocked on D4 (actual comp-plan rules from
Ish).

- `FinanceService` (or a new thin `CommissionService` if
  `FinanceService` would otherwise mix unrelated concerns — decide at
  implementation time, not here) gains `record_commission`,
  `reverse_commission`, `list_commissions_for_rep`,
  `get_team_commission_summary` (gated behind D2's permission), all
  writing/reading B8.1's append-only ledger.
- Rep-facing "This Month" panel (request §19) and manager-facing
  rankings panel, both server-computed, both reusing
  `AnalyticsSearchService` patterns rather than a third aggregation
  path.
- **Exit criterion:** a `CONTRACT_SIGNED`-equivalent action (see B8.12)
  produces exactly one `pending` ledger row per commission-eligible
  party, a chargeback produces a linked reversal row, and the rep
  dashboard total always equals `SUM(status='earned' or 'paid')` —
  verified by a test that reproduces the exact bug shape B6's
  `NEW-259` incident warns about (code-complete ≠ correct; this gets a
  real, not mocked, DB-backed test).

### B8.8 — Insurance restoration workflow & financing tracking (request §21, §22)

- **`InsuranceClaim`** table (net-new): `id`, `property_id`,
  `customer_id`, `carrier`, `claim_number`, `adjuster_name`,
  `adjuster_contact`, `date_of_loss`, `loss_type`, `status`
  (`reported`→`inspection`→`documentation`→`estimate`→`carrier_review`→
  `supplement`→`approved`→`contract`→`production`, matching the
  request's stated chain), `coverage_amount`, `deductible`,
  `supplement_amount`, `notes`. Linked from `Property`/`Project`, photos
  via existing `Document`.
- **`FinancingRecord`** table (net-new): `id`, `project_id`, `provider`,
  `application_status`, `amount_financed`, `customer_contribution`,
  `document_ids_json`, `status`. **Manual-entry only until D5 is
  answered** — no external financing API integration assumed.
- **Exit criterion:** an insurance-involved project shows claim status
  alongside the normal project record, with no separate insurance
  database — this is columns/tables in the same Core, queried the same
  way as everything else.

### B8.9 — Territory management & referral compensation (request §17, §20)

- Small: `territory` field (ZIP/county string or FK to a light
  `Territory` lookup table) on `User` (rep) and on `Lead`/`Customer`.
  Map view reuses existing address fields — no new geocoding service
  unless Ish asks for one; this phase is assignment/filtering, not a
  mapping platform build.
- Referral compensation is a `CommissionLedgerEntry` with
  `source_type='referral'` (B8.1) — **not** a new table, per §2's gap
  analysis.
- **Exit criterion:** leads can be filtered/auto-assigned by territory;
  a referral produces a correctly-attributed ledger row.

### B8.10 — Communications center & follow-up visibility (request §14, §15, §16, §31)

**Blocked on D1** (SMS) for anything beyond email + the existing
communication log.

- Unified communication view per customer/lead, reading
  `CommunicationRecord` (already logged from Aigentik's write-through
  per B6.6) — this phase adds the sales-portal read UI, it does not
  touch Aigentik internals (out of scope per B6.9: *"the SMS/email
  messaging agent itself... B6 calls it, does not modify its
  internals"* — same boundary applies here).
- Follow-up sequences: extend `AutomationRule`/`generate_cadence_tasks`
  (already exists) with rep/manager visibility and override — *"no
  black-box automation"* per the request is satisfied by making every
  rule and its next scheduled task readable and editable in this UI,
  not by adding new automation infrastructure.
- Notification center: **poll-based** (D3), reusing `NotificationService`.
- **Exit criterion:** every communication auto-attaches to the correct
  customer/lead record (already true at the data layer — this verifies
  the UI reflects it), and a rep can see and pause any pending automated
  follow-up before it fires.

### B8.11 — AI Sales Copilot (request §8, §27, §28)

Lowest priority, most speculative, explicitly last. Depends on `ccos/`,
a separately mid-build layer (`CODEY_MASTER_PLAN.md` §3.2) — this phase
does not start until that layer's own roadmap reaches a state where it
can serve a read-only advisory query over Core data. Scope, when
started: read-only summarization/recommendation over existing
Customer/Property/Communication/Estimate data, surfaced as text in the
dashboard and appointment-prep views — **never** a write path, never a
second copy of CRM data inside CCOS memory. Full scoping deferred to a
`project-architect` pass at that time; not designed further here.

### B8.12 — Sales-to-production handoff & job visibility (request §23, §24)

**Rule-4 category** (RBAC narrowing — sales must not gain production
write access).

- `ProductionHandoffChecklist` table (net-new, small): `id`,
  `contract_id`, `required_items_json` (scope, materials, customer
  selections, permits, insurance info, financing, deposit status — all
  *references* into existing records, not copies), `completed_at`,
  `completed_by`.
- Guard condition: production job creation checks contract-signed +
  deposit-received (existing `Contract`/`Invoice` status fields) before
  allowing the checklist to close — this is the "no production handoff
  until required contractual conditions are satisfied" rule from the
  request's §12, implemented as one validation, not a new state
  machine.
- Read-only job-status view for sales reps into `Project`/`WorkOrder`,
  explicitly **not** grantable write access — reuses the existing
  permission-narrowing pattern (`PERM_READ_ASSIGNED_PROJECTS` already
  exists in `auth.py`) rather than inventing a new one.
- **Exit criterion:** a sales rep can see job progress but a permission
  test proves they cannot call any production-mutating route; the
  handoff checklist cannot be marked complete against an unsigned
  contract.

### B8.13 — Mobile-first pass & audit completeness (request §32, §34)

- Sweep every new B8.x write path against the B6.2 audit standard
  (old/new values, not just new-state dumps) **before** this phase is
  called done — this is the same debt class B6.2 exists to close, and
  B8 should not reproduce it.
- Mobile QA pass on every new panel: single-column layout intact at
  phone width, tap targets sized per the existing drawer/button
  classes, camera/photo upload flow tested on-device (not just unit
  tested) per `CLAUDE.md`'s "test the golden path in a browser" rule.
- **Exit criterion:** verbatim `git diff` showing every B8 write path
  logs old+new values; a live-verifier pass confirms the mobile flows
  (assessment photo capture, e-signature, one-tap call/SMS) actually
  work on the target device, not just in a desktop browser.

### B8.14 — Analytics rollups (request §26)

- Rep/manager/executive tiers of reporting, all extending
  `AnalyticsSearchService.get_executive_dashboard` and
  `get_pipeline_summary` rather than building a parallel reporting
  engine. Forecast views (pipeline-weighted-by-probability) are a
  computation over existing `Opportunity.probability` +
  `estimated_value`, already modeled fields.
- **Exit criterion:** the three-tier dashboards (§26 of the request) are
  three permission-gated views of the same underlying aggregation
  query, not three separately maintained ones.

---

## 6. Cross-system linkage — stated explicitly per phase family

| System | What the sales portal does with it | What it must never do |
|---|---|---|
| **Codey-OS Core (`restoricon_core`)** | Every phase above reads/writes through its services and API. This is the system of record for every entity in this plan. | Never gets a second schema for the same concept (see §2's referral-vs-new-table example). |
| **Codey-Aigentik** | B8.10 reads `CommunicationRecord`/`Appointment` rows Aigentik already writes through (`calendar.js`, `external_id` idempotency per B6.7). B8.5/B8.6 may trigger existing Aigentik-sent notifications (confirmation, follow-up) the same way B6.6 already does. | Never modified internally by this plan (explicit B6.9 boundary, reaffirmed for B8). No new Aigentik-side data store. |
| **`restoricon` website** | Already the *source* of two flows this plan wires to, not replaces: `submit_public_lead` (contact/quote forms) and `submit_public_booking` (booking forms) both land directly in the Core via the existing public API, becoming `Lead`/`Appointment` rows a rep sees in B8.2/B8.3. B8.6's package tiers must not contradict `home-care.html`'s real HomeCare Basic/Plus/Complete/Estate naming. | Never gets its own lead/customer storage; it is a public-facing surface over the same Core API, same as the portal. |
| **CCOS (`ccos/`)** | Only B8.11, and only read-only. | No CRM data duplicated into `ccos_memory`; no write path from CCOS into the Core in this plan. |

## 7. What this plan deliberately does not do

- Does not add a message/event bus — none exists (§1.2); `AutomationRule`
  matching is the mechanism, extended where needed, not replaced.
- Does not add real-time push (D3) — every "live" panel is refetch-on-load.
- Does not touch `appointments`' schema (Aigentik's write-through
  target) — every appointment-adjacent addition is a sibling table.
- Does not build a financing-provider integration until D5 is answered.
- Does not restate Appendix C's field lists — see the header note.
- Does not activate anything under `CODEY_MASTER_PLAN.md` rule 1
  (self-improvement gate) — B8.11's "AI Copilot" is a read-only query
  surface over an already-serving model, not a self-improvement engine.

## 8. Next steps

1. Log the unfiltered-`/api/v1/projects` sales-portal gap (§1.1) to
   `NEW_ISSUES.md` as its own `NEW-###`.
2. Take Open Decisions D1–D5 (§4) to Ish; record answers in
   `CODEY_MASTER_PLAN.md` §8 the same way every other open decision is
   recorded, with the date and Ish's exact framing.
3. Add this file to `CODEY_MASTER_PLAN.md` §6 as **6.12 Track B / Phase
   B8 — Sales Rep Portal**, one-paragraph summary + pointer to this
   document, plus an Appendix A entry per `B8.1`…`B8.14` (unchecked).
4. Route B8.1 (the only phase with no open-decision blocker other than
   D2) through the standard pipeline: `project-architect` scopes the
   exact migration, `implementer` builds it, `code-reviewer` reviews it
   (rule-4, mandatory), `live-verifier` confirms against the real
   `~/.codeyOS/restoricon.db` schema before it's called done.
