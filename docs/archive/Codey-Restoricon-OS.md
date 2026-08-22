**ARCHIVED 2026-08-21 (Ish's explicit instruction).** Superseded by
`CODEY_MASTER_PLAN.md` in the repo root. This document's "PENDING NEXT
STEP" note asked for exactly that merge; it has now been done. Every
REAL/DESIGNED/PROPOSED decision from Revisions 1-6 was treated as settled
input and carried forward — the business layer now lives in the master
plan's Sections 1, 3, 6 (Track B), 7, 8, and Appendix C. Kept here as the
evidence trail for the reasoning behind each revision. **Do not plan work
from this file.**

---

# Codey-Restoricon-OS

**Status of this document: living planning document, design-only. No code
has changed as a result of it. It is subordinate to
`CODEY_OS_MASTER_VISION.md`, which remains the authoritative spec — this
document does not contradict it, and where it implies an amendment to the
vision doc or `TODO.md`, that amendment is listed as a proposal awaiting
Ish's explicit, logged sign-off (per CLAUDE.md rules 1 and 8), not enacted
here. This document does not restate `TODO.md`'s ordering — it points at
it. Created 2026-08-21. Revision 2 (same day, shared-model + CRM-module
feedback). Revision 3 (same day): Codey-OS confirmed as the single
backend/API for all business data; Aigentik and Private-Agent narrowed to
executor/client roles; phone-hosted website with owner/staff/customer
surfaces confirmed as a Jan-1 target. Revision 4 (same day): Ish confirmed
every domain — not just CRM/Sales and Operations — is a Jan-1, 2027
target. §8 rewritten around a full-scope target with an internal build
sequence, rather than a scope cut. Revision 5 (same day): retired the
"three runtime agents" framing — Codey-OS is one brain with two limbs
(Aigentik, Private-Agent) that differ by what they can physically reach,
not by rank. Aigentik-CLI's Node.js code stays as-is (no rewrite into
Codey-OS's Python process) but becomes a Codey-OS-supervised process
rather than an independently-run one. Revision 6 (same day): narrowed
Revision 5's decision — Codey-OS supervises a **fork**, not the public
repo. Aigentik-CLI and Private-Agent both stay untouched, standalone
open-source products; two new forked repos, **Codey-Aigentik** ("Codey-OS's
voice and inbox") and **Private-Codey-Agent** ("Codey-OS's eyes, hands,
ears, and voice"), carry the Codey-OS-integration changes instead.**

**PENDING NEXT STEP — not yet executed, noted here for a future session:**
Ish wants this document combined with Codey-OS's current tracking/spec
docs — `CODEY_OS_MASTER_VISION.md`, `TODO.md`, `WORK_QUEUE.md`,
`PROJECT_PLAN.md`, `PROJECT_LOG.md`, and `NEW_ISSUES.md` — into one new
**master phase plan** that supersedes all of them, rather than living
alongside them as a subordinate document the way it does today. This is
deliberately not done in this session: Ish plans to restart with a fresh
context window and a stronger model specifically so nothing from any of
those source documents gets missed or dropped in the merge. Whoever picks
this up next should treat every REAL/DESIGNED/PROPOSED-labeled decision
recorded in this document (Revisions 1-6) as settled input to that new
plan, not re-litigate them — the merge's job is combining and
resequencing, not re-deciding what's already been decided here.

Every claim below is labeled **REAL** (exists today, verified by reading
the code/docs), **DESIGNED** (written down as intended architecture but
not built), or **PROPOSED** (a recommendation this document is putting in
front of Ish, not yet a decision). Don't read anything here as describing
current running behavior unless it says REAL.

---

## 1. What this document is for

Ish is running an actual construction/restoration business — **Restoricon,
LLC** (Hartford County, CT; general remodeling, kitchens/baths, structural
repair, and a Pre-Claim damage-assessment service) — and wants Codey-OS to
grow into the operating system for that business, not just a coding agent.
This document works out how the pieces that already exist, and the pieces
that don't, fit together into one system, and what's realistic to build
between now and **January 1, 2027** (~4 months, solo).

This is the business-layer instantiation of `CODEY_OS_MASTER_VISION.md`
Section 9's multi-agent platform direction (2026-08-05 amendment).

**Ish's own summary of the core idea, the north star for every design
choice below**:

> CRM = memory. Agents = workers. Aigentik = communicator/orchestrator
> of communication. Calendar = time. Accounting = money.

**And the settled shape, as of this revision**: Codey-OS is the operating
system, and — new in this revision — **the single backend all business
data lives in and all business logic runs against.** Aigentik-CLI and
Private-Agent are not peers holding their own data anymore; they narrow
into an executor and a client. §3 works through exactly what each keeps
and gives up.

---

## 2. The three real systems today (verified, not aspirational)

### 2.1 Codey-OS (`~/Codey-OS`) — **REAL**, the platform — becoming the backend too

CCOS (`ccos/`) is the OS shell: capability registry, plugin manager,
resource gate (Phase 1 of the vision doc's rollout order, currently
mid-build; NEW-145/NEW-152's lazy-coder-load fix landed 2026-08-21,
live-verification still pending), daemon, device manager. The coding
agent (`core/`) is registered as the first capability.

New in this revision: Codey-OS also becomes **the Core's data store, its
API, and the host of the Restoricon website** (§4). Today none of that
exists — this is entirely DESIGNED, not built.

### 2.2 Aigentik-CLI (`~/Aigentik-CLI`) — **REAL** today; role narrows going forward

Today: a standalone Node.js process with its own JSON data store
(contacts, calendar, rules, profile), watching Gmail via IMAP IDLE and
handling Google Voice SMS (forwarded as email), with its own `llama-server`
(Qwen3-4B). Its `contacts.json` already models a customer/lead/
subcontractor directory (see Revision 1's §2.2 detail, unchanged as a
factual description of what exists) — that data is real and valuable, and
§3.2 covers what happens to it.

**Going forward (DESIGNED, this revision)**: Aigentik keeps exactly one
job — being the execution surface for the communication channels it
already speaks natively (Gmail/SMTP-IMAP, Google Voice SMS-over-email).
It stops owning data. Anything it collects or observes gets written
through to Codey-OS's Core instead of its own `data/*.json`.

**Decided in Revision 6**: `~/Aigentik-CLI` itself stays untouched — it
remains a standalone, general-purpose open-source product for anyone,
with its own users and its own install path, unrelated to Restoricon.
The Codey-OS integration work (dropping the local JSON store, writing
through to the Core) happens in a **new forked repo, `Codey-Aigentik`**
("Codey-OS's voice and inbox") — a git fork of `Aigentik-CLI` so upstream
fixes (IMAP-reconnect handling, parsing edge cases, etc.) can still be
pulled in via `git fetch upstream` rather than re-derived by hand. Codey-OS
supervises *that* fork's process as `agent_type: external_process`
(§3.2), not the public repo. This is a real, ongoing two-codebase cost —
forking doesn't eliminate drift, it just gives git tooling to manage it;
a fix made in `Codey-Aigentik` that also matters to public Aigentik-CLI
users still has to be ported back by hand, since the public repo won't be
tracking the fork as its own upstream.

### 2.3 Private-Agent (`~/private-agent`) — **REAL** today; role narrows and gains new jobs

Today: a Flutter Android app driving other apps via the accessibility
tree and an LLM (local-capable, confirmed by Ish; OpenAI-compatible client
with a configurable base URL). One-shot device actions, voice I/O,
wake-word (beta), Telegram remote control. Everything persists in
`SharedPreferences` — no server component.

**Going forward (DESIGNED, this revision)**, Ish's own framing: Private-
Agent becomes the business's **eyes, hands, ears, and voice** — a pure
device-action executor, plus a **dashboard client** displaying business
data it doesn't own. Concretely:
- **Device actions Aigentik can't reach**: anything requiring driving a
  third-party app's UI via accessibility — Facebook Messenger, WhatsApp,
  posting to a social media app — not just the one-shot calls/SMS/alarms
  it already does.
- **Scheduled commands from Codey-OS**: e.g. "post this to Instagram at
  9am," "text this subcontractor in WhatsApp." This requires Codey-OS to
  have an outbound dispatch path to an Android app it doesn't run in the
  same process — new mechanism, not something either repo has today (see
  §6.3).
- **A dashboard UI**: business calendar, financial summary, contacts —
  all displayed in the app, all *fetched from* Codey-OS's Core, none of
  it stored or owned locally beyond normal client-side caching. Private-
  Agent is a read (and, for scheduled actions, write-triggering) client
  of the same API the website surfaces use (§4.2) — not a second data
  store.

**Decided in Revision 6**, same reasoning as Aigentik (§2.2): `~/private-agent`
itself stays untouched — it remains its own standalone, general-purpose
open-source product (already a fork of `orailnoor/private-agent`, with its
own users). The Codey-OS-integration work (the dashboard, scheduled-command
handling, narrowing toward pure executor+client) happens in a **new forked
repo, `Private-Codey-Agent`** ("Codey-OS's eyes, hands, ears, and voice") —
a git fork of `private-agent`, same upstream-pull rationale as
`Codey-Aigentik`.

### 2.4 Restoricon (`~/restoricon`) — **REAL**, but becoming the customer/staff-facing surface, not staying a static site

Today: static marketing site, no backend, `mailto:` lead forms.
**Going forward (DESIGNED, this revision, target Jan 1, 2027)**: hosted
**on the phone**, backed by Codey-OS's Core API, with two logged-in
surfaces layered onto the existing public marketing pages:
- A **customer portal** — customers log in and see their own project data.
- A **staff/admin page** — not "hidden" as a security mechanism (obscurity
  isn't authorization — see §3.3), but a real authenticated admin surface
  using the same role/permission system as the customer portal, just a
  different role.

`llms-full.txt` remains a ready-made factual reference for business
persona/facts, reusable as seed content for the Core's business-profile
record.

---

## 3. The settled architecture

### 3.1 Codey-OS is the OS, the backend, and the orchestrator — mechanism, not policy

Codey-OS owns **mechanism**: the schema, canonical IDs, the API, model
access arbitration (§4), authentication/roles/permissions, the audit log,
the search index, the task/event queue, hosting the website, and — new
in this revision — **outbound dispatch to Private-Agent** and **backup/
maintenance scheduling** (§6.3, §7). It never owns **policy**: what a lead
score means, when a follow-up fires, what a warranty claim requires, which
subcontractor gets assigned a job. Domains (§5.3) own policy, expressed as
rules and workflows running over the Core's data. This is continuous with
how Codey-OS is already built — `capability_registry`/`plugin_manager` are
mechanism today; the plugins registered through them carry policy.

### 3.2 One brain, two limbs — not three peer agents

**Revision 5 correction**: earlier revisions of this document counted
Codey-OS, Aigentik, and Private-Agent as "three runtime agents," which
reads as three peers competing for identity. That's not the shape. It's
**one brain (Codey-OS) with two limbs that differ by what they can
physically reach, not by rank**:

- **Aigentik is the voice/inbox limb** — it executes the channels it
  speaks natively: Gmail/IMAP-SMTP, Google Voice SMS-over-email. IMAP
  IDLE holds a live protocol connection open and works with the screen
  off; nothing about that needs — or benefits from — a visible app.
- **Private-Agent is the screen/hands limb** — it executes everything
  that only exists behind a third-party app's UI (Messenger, WhatsApp,
  social posting), plus device-native one-shot actions (calls, SMS,
  alarms), plus scheduled commands dispatched from Codey-OS. It also
  renders a dashboard of Core data (calendar, financials, contacts) it
  never owns a copy of beyond client-side caching.

**These two limbs cannot be collapsed into one process.** Codey-OS's
Python process has no access to Android's accessibility APIs; Private-
Agent's Flutter/Dart layer isn't built for IMAP IDLE or SMTP. The
three-process shape isn't an accident of history or a rank ordering —
it's a direct consequence of what each runtime can physically talk to.

**Should Aigentik's comms logic be rewritten into Codey-OS's own Python
process, to get down to two processes?** Considered and rejected for this
build. `index.js` + `email-provider.js` + `owner-command.js` are ~120KB
of already-debugged IMAP-reconnect handling, Google-Voice-SMS-as-email
parsing, deterministic date parsing, and natural-language command
interpretation, on a system in daily production use right now — rewriting
that against a Jan-1 date that already carries every domain plus the full
portal (§8) is high-risk for little gain. It's little gain specifically
because `core/resource_gate.py` already arbitrates by `model_id` across
multiple named roles (`primary`, `planner`, and elsewhere embed) rather
than a single flat "is a model loaded" check — folding Aigentik's model
calls in-process would just add one more `model_id` to a gate already
built for several, not simplify anything architecturally.

**Decision: Aigentik's Node.js code stays exactly as it is, but stops
being independently run.** Codey-OS supervises it — starts it, stops it,
monitors it — as `agent_type: external_process`, the path
`docs/agent-plugin-blueprint.md` §4.2 already designed for exactly this
case. This gets "Codey-OS runs everything, nothing is a peer" without
touching a working production system. It needs process-supervision
plumbing in `ccos/core/plugin_manager.py` that doesn't exist yet — real,
scoped work (§7 tracks it), not a rewrite. Private-Agent, being a
separate Android app with no equivalent local-supervision path today,
keeps its own process lifecycle (started/stopped on-device) but is the
same kind of limb conceptually — a Codey-OS-orchestrated executor, not a
peer with its own identity or data.

**Both limbs write through to the Core, never keep their own store**:
Aigentik's contact/calendar/communication-history records, and Private-
Agent's dashboard reads, all go through the same Core (§4, §5) — from the
Core's point of view, "who handled this interaction" is metadata on one
shared Communication History record type (§5.2), not two separate
histories kept by two separate systems.

### 3.3 Three client surfaces, one API, one auth system

Owner/staff via Private-Agent's dashboard, staff/admin via the website's
authenticated admin page, and customers via the website's customer
portal are **three clients of the same Core API**, distinguished by role,
not by separate implementations. This is the load-bearing simplification
that keeps three surfaces from tripling the actual build: there is one
data layer, one API, one auth/permission system: write it once, every
surface consumes it the same way, just filtered by role.

Because a customer-facing login now exists, **roles and permissions are
not deferrable** — the moment a customer can log in and see project data,
a bug in that boundary means one customer sees another's contract. There
is no "hidden page" shortcut around this: an unauthenticated admin URL
that's merely unlinked is not a security boundary, it's the same login
system with a different role assigned. This forces auth/roles into Jan-1
scope (§8) — it was optional in this document's earlier drafts; it isn't
anymore, because the surfaces built to depend on it are now in scope too.

---

## 4. The Core and the shared model layer

### 4.1 The Core — same four layers as Revision 2, now explicitly hosted by Codey-OS

Unchanged reasoning from the prior revision, restated briefly (full detail
and Appendix A's verbatim source list are unchanged):
- **5.1-equivalent — Core schema/entities**: Customer, Lead, Opportunity,
  Project/Job, Estimate, Proposal/Contract, Document, Invoice/Payment,
  Employee/User.
- **5.2-equivalent — Core services**, owned by Codey-OS, cross-cutting:
  Communication History, Tasks/Follow-ups, Calendar, Global Search, Audit
  Log. Communication History and Audit Log remain day-one-or-never
  (append-only, can't be backfilled).
- **5.3-equivalent — Domain behavior**: Automated Workflows, Marketing,
  Customer Service, Reporting/Dashboard — business rules over the schema,
  using the services.
- **5.4-equivalent — Surfaces**: now concretely three (§3.3), plus
  external integrations (Gmail, calendars, ad platforms, payment
  processors, accounting software, e-signature).

(This document keeps the layer definitions in §5 below rather than
renumbering everything a third time — §4 introduces what's new this
revision, §5 keeps the layer breakdown intact for reference.)

### 4.2 Deployment: phone first, confirmed — portability is a design principle, not a build item

Confirmed: **everything runs on one phone to start**, including the
Core, the API, and the website. Migrating later to Firebase or a larger
server is the acknowledged future direction, **not decided and not
designed here**. The only thing this document commits to now: the Core's
API should not bake in assumptions that only work when the client and the
server are the same device (e.g. no shared-memory shortcuts between the
website's backend code and Codey-OS's Python internals) — a plain HTTP/
API boundary, even when both sides happen to run on the same phone today,
is what keeps a future move to different hardware from being a rewrite.
That's a design discipline to hold while building, not a project to do
now.

**Also confirmed and explicitly deferred**: scheduled maintenance
windows and periodic backups to another storage location. Real
requirements, genuinely "to be figured out" per Ish — named here as part
of Codey-OS's mechanism list (§3.1) so they aren't forgotten, not
designed in this revision.

### 4.3 The shared model layer — unchanged from Revision 2

One shared local model server, one port, used by Codey-OS, Aigentik, and
Private-Agent, with Codey-OS tracking access so nothing gets crossed.
Two distinct problems inside that:
- **Concurrent requests** — likely already solvable via `llama-server`'s
  slot/`--parallel` handling; unverified in this repo today (no such flag
  is set anywhere Codey-OS launches `llama-server`). Test directly before
  building anything more elaborate.
- **Model residency** — ~10.8GB can't hold every model simultaneously
  resident (rule 2). Codey-OS must arbitrate which model is loaded and
  who may trigger a swap — this is `CODEY_OS_MASTER_VISION.md` §11's
  Model Orchestrator direction, currently parked in `TODO.md` Phase 2
  until a domain agent needing it is scoped. This document is that
  scoping trigger, pending Ish's confirmation.
- **The open fork, still Ish's call**: can one model serve coding tasks,
  customer-facing prose, and Private-Agent's on-screen reasoning well
  enough to avoid swap-scheduling entirely? Test the concurrency question
  first, then decide — not resolved here.

---

## 5. The Core — four layers (reference, unchanged structure from Revision 2)

### 5.1 Core schema — entities (Appendix A modules 1, 2, 3, 7, 8, 9, 10, 11, 16)

Customer, Lead, Opportunity, Project/Job, Estimate, Proposal/Contract,
Document, Invoice/Payment, Employee/User — canonical IDs everything else
references (§3.1's "Finance holds `customer_id = 1842`, not its own
copy" rule).

### 5.2 Core services — cross-cutting, owned by Codey-OS (Appendix A modules 4, 5, 6, 19, 20)

Communication History, Tasks/Follow-ups, Calendar, Global Search, Audit
Log. Every domain uses these; none owns one. Communication History and
Audit Log are day-one-or-never (§4.1) — everything else here can be added
later without permanent data loss.

### 5.3 Domain behavior — business rules over 5.1, using 5.2 (Appendix A modules 13, 14, 15, 18)

Automated Workflows, Marketing, Customer Service, Reporting/Dashboard.
CRM/Sales, Operations, Finance/Bookkeeping, Compliance, HR, Customer
Service, Procurement each own their slice of rules here, none of them
duplicating 5.1's data.

### 5.4 Surfaces & integrations (Appendix A modules 12, 21) — now concrete, see §3.3

Private-Agent's dashboard, the website's staff/admin page, the website's
customer portal — three clients, one API, one auth/role system.
Integrations (Gmail, calendars, ad platforms, payment processors,
accounting software, e-signature) remain as previously scoped.

---

## 6. Integration gaps, confirmed real

### 6.1 Port-probe adoption vs. a shared model server

Unchanged from Revision 2: `core/loader_v2.py` decides "is my coder
server already running?" by probing port 8080 — the same adoption path
involved in this session's NEW-145/NEW-152 fix. A shared model server
needs an explicit lease/registry, not a port-occupancy guess that
`core/embed_server.py`'s `_kill_port_occupant()` can currently act on.

### 6.2 Private-Agent's model source — non-issue, confirmed

Already run locally by Ish; pointing it at a shared local endpoint is a
config change. No blocker.

### 6.3 New this revision: Codey-OS has no outbound path to Private-Agent

Displaying a dashboard is a straightforward read (Private-Agent calls
Codey-OS's API). **Dispatching a scheduled command the other direction —
Codey-OS telling Private-Agent's phone to do something at a given time —
is new mechanism that doesn't exist in either repo today.** Private-Agent
already maintains a background Telegram Bot API polling connection for
remote control — that's a plausible existing transport to reuse rather
than invent a new one, but this document doesn't design the protocol.
Flagged here as a real gap, not solved.

---

## 7. Open questions for Ish

Trimmed from Revision 2 — four of the five prior open questions are now
answered by Ish's direction in this revision (phone hosts the website;
Aigentik migrates its data rather than syncing; Codey-OS is confirmed as
the Core's home; the portal/permissions coupling is resolved by making
auth Jan-1 scope). What's left:

1. **Resolved in Revision 6**: both Aigentik-CLI and Private-Agent stay
   untouched, standalone open-source products; the Codey-OS-integration
   work lives in two new forked repos, `Codey-Aigentik` and
   `Private-Codey-Agent` (§2.2, §2.3, §3.2). No longer open.
2. **The Core→Private-Agent dispatch mechanism (§6.3)** — reuse the
   existing Telegram Bot API channel, or build something Codey-OS-native?
   Not designed here.
3. **§4.3's one-model-vs-swap-scheduling fork** — test the concurrency
   question first, then decide.
4. **Deployment migration path off-phone (§4.2)** — Firebase, a bigger
   server, or something else — explicitly not decided, revisit after the
   phone-hosted version is real.
5. **Backup/maintenance windows (§4.2)** — explicitly deferred, "to be
   figured out."

---

## 8. The January 1, 2027 target — full scope, sequenced (rebuilt this revision)

**Confirmed by Ish: this is no longer a cut line.** Every domain named in
this document — CRM/Sales, Operations, Finance/Bookkeeping, Marketing/
Lead-Generation, Compliance, HR, Customer Service, Procurement — is a
Jan-1, 2027 target, not a stretch goal deferred past it. So is the
phone-hosted website with all three surfaces, and both Aigentik's and
Private-Agent's full role as described in §2-§3, including Private-Agent's
third-party-app communication/scheduled posting and the customer portal's
full document/signature/financial surface.

This section stops being about what to cut and becomes about **what has
to be built before what**, since even a full-scope target has a real
dependency order — nothing downstream of the Core can be built before the
Core exists, and that ordering is the actual project plan, not this
document's call to soften. Ish should treat the sequence below as a
working default to adjust, the same way earlier revisions' cut lines were
— it is still **PROPOSED** ordering, even though the destination (full
scope) is now a settled decision.

**PROPOSED build sequence, all landing by Jan 1, 2027:**

1. **The Core's foundation** — schema/canonical IDs (§5.1), the API,
   auth/roles/permissions (§3.3), and the day-one-or-never services
   (Communication History, Audit Log — §5.2). Nothing else can start
   for real until this exists; it's the dependency root for every domain
   and every surface.
2. **The shared model layer** (§4.3) — the concurrency test, the
   one-model-vs-swap decision, and the lease/registry replacing
   port-probe adoption (§6.1). Needs to land early because Aigentik's
   migration, and every domain that wants AI-assisted behavior (lead
   scoring, drafted follow-ups, financial-pattern flags), depends on it
   existing and being safe to share.
3. **Aigentik's write-through migration** (§3.2) — it stops owning
   `data/*.json` and writes through to the Core. This is also when
   CRM/Sales gets its first real data (Aigentik's existing contacts are
   the seed).
4. **CRM/Sales and Operations domains** — the two with the most existing
   groundwork (Aigentik's contacts, `.ics`-based scheduling) and the ones
   every other domain implicitly assumes exist (Finance needs jobs to
   invoice against; Marketing needs leads to report on; Compliance needs
   subcontractor records to monitor).
5. **The phone-hosted website** (§2.4, §4.2) — public site plus the two
   logged-in surfaces (staff/admin, customer portal), now including the
   portal's full document/signature/financial detail rather than a
   view-only stub, and Private-Agent's dashboard (§2.3) as the third
   client of the same API.
6. **The remaining domains** — Finance/Bookkeeping, Marketing/Lead-Gen,
   Compliance monitoring/alerting, HR, Customer Service, Procurement.
   These can build in parallel with each other once step 1-2 exist, since
   none of them depend on one another the way step 4's domains are
   depended on — but each is real, scoped work, not a checkbox toggle:
   Finance's invoicing/payment tracking, Marketing's campaign/ad
   integrations, Compliance's expiration monitoring and alerts, HR's
   onboarding/recruiting flows, Customer Service's ticketing, and
   Procurement's vendor/PO tracking all need their own schema work on top
   of §5.1's shared entities and their own domain rules (§5.3).
7. **Private-Agent's third-party-app communication and scheduled
   dispatch** (§6.3, §2.3) — Messenger/WhatsApp/social-posting automation
   and the Core→Private-Agent scheduled-command mechanism. This is the
   piece with the least existing groundwork in either repo (§6.3's
   dispatch protocol isn't designed anywhere yet) — sequenced last because
   it has the most net-new mechanism to invent, not because it matters
   less.
8. **Formal CCOS plugin registration** of Aigentik-CLI/Private-Agent as
   `agent_type: external_process` — independent of whether they're Core
   clients (they can be, and should be, well before this step), and
   still gated on Phase 1's resource gate being fully live-verified
   per the vision doc's own rollout order. If Phase 1 isn't live-verified
   by the time everything else above is ready, this step alone may slip
   past Jan 1 without blocking anything the business actually needs day
   to day — flagged now so that specific dependency is visible.

**The one honest caveat this document keeps, even with full scope
confirmed**: step 8, and step 8 alone, has an external dependency (Phase
1's live-verification) that this document can't promise a date for — not
because the scope was softened, but because it's gated on work already
described as pending in `TODO.md`. Everything else above is scoped as a
Jan-1 commitment.

---

## 9. Relationship to existing tracking docs

- `CODEY_OS_MASTER_VISION.md` stays authoritative for platform
  architecture; this document does not amend it. This revision's
  confirmation that Codey-OS is the Core's backend, hosts the website, and
  needs an outbound dispatch path to Private-Agent is a genuine amendment
  to vision doc §9 (and touches §11's Model Orchestrator via §4.3) — it
  remains a **proposal** for a future explicit, logged decision from Ish,
  not an enacted change.
- `WORK_QUEUE.md` Track 3.5's three unscoped items (resource-bus design,
  manifest schema extension, Aigentik-CLI integration scoping) are given
  concrete shape by this document's §4/§5/§6 — to be scoped through the
  normal project-architect pipeline once Ish confirms direction, not
  built from this document directly.
- `TODO.md` remains the single ordered checklist; this document does not
  duplicate or reorder it.

---

## Appendix A — Ish's CRM module breakdown (verbatim source, 2026-08-21)

Unchanged from Revision 2 — kept verbatim, in one place, so future edits
to field lists happen here once instead of drifting between two
descriptions of the same thing.

1. **Customer/Contact Management** — Customer ID, first/last name,
   company name, phone numbers, email addresses, mailing address,
   service/property address, customer type (residential/commercial),
   customer source, assigned employee/agent, customer status (lead/
   prospect/active/past/lost), tags, notes, custom fields, date created,
   last contact, next follow-up, customer history. *Keep customer
   information separate from individual jobs/projects — one customer can
   have multiple projects.*
2. **Lead Management** — manual/website/phone/email/social/referral/
   advertising lead creation, lead source tracking, status, score, value,
   assigned salesperson, first/last contact, next follow-up, notes,
   convert to customer/opportunity, mark lost + reason. Example chain:
   *Google Ads → Phone → Roof repair → Insurance claim → $18,000
   potential job.*
3. **Sales Pipeline** — stages (New Lead → Contacted → Appointment Set →
   Estimate → Proposal Sent → Negotiating → Won/Lost); each opportunity:
   ID, customer, project, estimated value, probability, pipeline stage,
   expected close date, assigned employee, competitor info, notes, tasks,
   communications, documents, activity history. Produces a sales
   forecast view (opportunity/value/stage/probability table).
4. **Communication History** — phone, email, SMS, voicemail, website
   chat, social messages, internal notes, AI conversations, appointment
   communications; each record: who, when, channel, direction, subject,
   message/content, employee/agent, related customer/project/opportunity.
5. **Tasks & Follow-Ups** — create/assign/due date/priority/status,
   recurring tasks, follow-up reminders, automated follow-ups, overdue
   tasks, task history.
6. **Calendar/Scheduling** — appointments, site visits, estimates,
   inspections, installations, follow-ups, employee/customer availability,
   multiple employees/calendars, confirmation, reminders, rescheduling,
   cancellation, recurring appointments, travel time, calendar sync.
7. **Projects/Jobs** — project ID, customer, property, type, status,
   start/expected/actual completion, project manager, assigned employees,
   subcontractors, scope of work, estimated/contract/actual cost, profit,
   documents, photos, notes, tasks, communications, change orders,
   payments, warranty info. *A customer isn't the same thing as a job —
   one customer can have several jobs across years.*
8. **Estimates/Quotes** — creation, number, line items, materials, labor,
   subcontractors, markup, tax, discounts, attachments, versions, send,
   customer approval/rejection, expiration, convert to contract/job.
9. **Proposals/Contracts** — creation, templates, digital signatures,
   storage, status, expiration, change orders, customer approval,
   signed-document storage, version history.
10. **Documents** — contracts, estimates, proposals, invoices, receipts,
    insurance documents, permits, photos, PDFs, customer uploads, signed
    documents, warranty documents; plus search, tags, versioning,
    permissions, expiration reminders.
11. **Billing/Payments** — invoice records, status, amount, due date,
    payments, deposits, balance, payment history, refunds, change orders,
    project financial summary. *A CRM doesn't need to be a full
    accounting system, but should track financial information;
    eventually connect a real accounting system rather than rebuild one.*
12. **Customer Portal** — project status, appointments, estimates,
    contracts, invoices, payments, messages, documents, photos, change
    orders, warranty info, approvals, signatures.
13. **Automated Workflows** — e.g. new lead → create customer → create
    opportunity → assign employee → send confirmation → create follow-up
    task → notify salesperson; estimate sent → wait 3 days → check
    response → follow-up if none → Aigentik sends it; appointment
    tomorrow → reminder → availability/confirmation checks → notify
    employee; job completed → request review → send invoice → schedule
    warranty follow-up → add to marketing campaign.
14. **Marketing** — email/SMS campaigns, segmentation, tags, marketing
    lists, campaign tracking, lead-source tracking, referral tracking,
    reactivation, review requests, automated campaigns, unsubscribe
    management. Example: filter customers with a 4+-year-old roof job
    into a reactivation campaign.
15. **Customer Service** — support tickets, complaints, service requests,
    warranty claims, issue tracking, priority, assigned employee, status,
    resolution, satisfaction. Example flow: warranty issue → ticket →
    assign technician → schedule visit → resolve → document → close.
16. **Employees/Users** — accounts, roles, permissions, departments,
    assigned customers/projects/tasks, employee calendars, activity
    history, performance metrics. Example role ladder: Admin → Manager →
    Sales → Project Manager → Technician → AI Agent.
17. **AI/Agent Layer** — the CRM exposes structured information to
    agents (Aigentik: communications/scheduling; Marketing Agent:
    campaigns/ads/social/lead-gen; Bookkeeping Agent: invoices/payments/
    expenses; HR Agent: employees/onboarding/documents/PTO; CRM itself:
    customer data/leads/opportunities/projects/activities/tasks/
    relationships) — *the agents shouldn't each maintain their own
    customer database; they should all talk to the same CRM data layer.*
    (Folded into §3 as the architecture principle, not a separate build
    item.)
18. **Reporting/Dashboard** — Sales (lead count/source/conversion rate/
    pipeline value/avg deal size/salesperson performance), Operations
    (active/overdue jobs, upcoming appointments, employee workload, open
    issues), Financial (contract value, revenue, outstanding invoices,
    project profitability, expected revenue), Marketing (cost per lead/
    customer, revenue by source, customer acquisition cost).
19. **Search** — global search across customer → leads → jobs →
    estimates → contracts → emails → SMS → appointments → payments →
    documents → tasks from one query, as a first-class feature.
20. **Activity/Audit Log** — every important action recorded with actor
    and timestamp (e.g. "Aigentik sent email... John opened proposal...
    John approved estimate... Project created... Appointment scheduled"),
    especially important once multiple humans and AI agents modify the
    same data.
21. **Integrations** — Gmail, Outlook, Google/Microsoft Calendar, SMS,
    phone system, Google Ads, Facebook, Instagram, TikTok, website forms,
    payment processor, accounting software, e-signature, cloud storage,
    maps, AI models.

**Ish's architecture summary, in his own words**: *"Don't think of the
CRM as one giant application. Think of it as the central business
memory."* CRM Core in the middle; Aigentik, Marketing Agent, Bookkeeping
Agent (and others) around it as workers operating on that memory, all
reading/writing the same underlying database rather than keeping private
copies. *"I would not make Aigentik the CRM. I'd make CRM the shared
business data layer, with Aigentik being the communications/assistant
agent that operates on that data."* This is exactly §3.1's mechanism/
policy split, stated from the data side instead of the process side.
