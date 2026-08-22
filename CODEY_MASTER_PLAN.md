# Codey Master Plan — the single authoritative plan

**Status: AUTHORITATIVE. Start here, every new chat/context window, for
every agent (Claude Code, Qwen CLI, Gemini CLI, or a human).**

Created 2026-08-21 by merging, and superseding, six previously-separate
documents:

| Superseded document | What was carried forward into this plan |
|---|---|
| `CODEY_OS_MASTER_VISION.md` | Platform identity, architecture, safety model, the 7.x/9.x/11.x planned architecture, non-goals |
| `Codey-Restoricon-OS.md` (Revisions 1–6) | The business layer: Restoricon Core, the two limbs, three surfaces, the Jan-1-2027 target |
| `TODO.md` | The ordered outstanding-work checklist (every open item, re-homed into §6 and Appendix A) |
| `WORK_QUEUE.md` | The evidence/reasoning behind each queue item (archived; cited, not restated) |
| `PROJECT_PLAN.md` | Phase status and the code-complete-vs-live-verified discipline |
| `PROJECT_LOG.md` / `NEW_ISSUES.md` | Demoted from "start here" to **appendix ledgers this plan owns** — see §9 |

All six now live in `docs/archive/` (except the two ledgers, which stay at
the repo root and stay append-only — see §9 for why). **Do not plan work
from the archived copies.** They are evidence, not instructions.

**Merge rule applied here, per the pivot note in the old
`Codey-Restoricon-OS.md`:** every REAL/DESIGNED/PROPOSED decision recorded
in Revisions 1–6, and every decision logged in the other five documents,
was treated as **settled input**. This merge combined and re-sequenced;
it did not re-decide anything already decided. Where two documents
described the same work under different names, they were collapsed into
one item (§6.0 lists every such collapse explicitly).

---

## 0. How to read this document

**Two labeling conventions are load-bearing and must never be flattened.
Both are carried forward from the superseded documents; keep using them
in every future edit.**

**Business-layer claims** are labeled:
- **REAL** — exists today, verified by reading the code/docs.
- **DESIGNED** — written down as intended architecture, not built.
- **PROPOSED** — a recommendation awaiting Ish's decision.

**Platform-layer claims** are labeled:
- **code-complete** — written, unit/mock-tested, possibly reviewed.
- **code-reviewer-approved** — passed the mandatory adversarial review.
- **live-verified** — proven on this device with real, verbatim output.

A thing is never "done" because it is code-complete. Rule 7 (§2) exists
because this project has been burned by exactly that conflation.

**Reading order for a fresh session:**
1. §2 (rules) — non-negotiable, overrides any default behavior.
2. §4 (where things actually stand today) — the current-state snapshot.
3. §6 (the plan) — find the phase the current work sits in.
4. Appendix A — the flat checklist of every open item.
5. Only then, if you need the *why* behind a specific line, open the
   archived source doc named on that line.

---

## 1. What this is

### 1.1 Two layers of the same system

**Codey-OS** is a local-first AI agent operating system running on
Android/Termux (Samsung S24 Ultra, ~10.8GB RAM, ~16GiB zram). It is a
fully-capable AI coding agent wrapped inside an OS shell (CCOS) that
registers, routes to, monitors, and eventually extends capabilities
beyond coding. Day-to-day it is called **Codey**.

**Restoricon OS** is what Codey-OS becomes when pointed at Ish's actual
business — **Restoricon, LLC** (Hartford County, CT; general remodeling,
kitchens/baths, structural repair, and a Pre-Claim damage-assessment
service). Codey-OS is not only the OS: it is **the single backend all
business data lives in and all business logic runs against**.

These are not two projects. The business layer is the first real
instantiation of the platform's own multi-agent direction (Ish,
2026-08-05): the coding agent is the first domain agent, not the whole
system.

### 1.2 The north star

Ish's own summary, the sentence every design choice below answers to:

> CRM = memory. Agents = workers. Aigentik = communicator/orchestrator
> of communication. Calendar = time. Accounting = money.

And, from the CRM breakdown (Appendix C):

> "Don't think of the CRM as one giant application. Think of it as the
> central business memory." … "I would not make Aigentik the CRM. I'd
> make CRM the shared business data layer, with Aigentik being the
> communications/assistant agent that operates on that data."

### 1.3 The date

**January 1, 2027 — full scope, confirmed by Ish (2026-08-21,
Revision 4).** Every domain — CRM/Sales, Operations, Finance/Bookkeeping,
Marketing/Lead-Gen, Compliance, HR, Customer Service, Procurement — plus
the phone-hosted website with all three surfaces, plus both limbs' full
roles, is a Jan-1 target, not a stretch goal. This is a settled decision
and is not re-litigated here. §7 states the risks against it honestly;
§6 states the order the work has to happen in.

---

## 2. Non-negotiable rules

These override any default agent behavior. Rules 1–11 are carried
verbatim in intent from `CLAUDE.md`, with rules 7/8/9 re-pointed at this
plan's own successor documents.

1. **Self-improvement mechanisms** (`goal_engine`, `auto_improvement_loop`,
   `capability_optimizer`, `skill_recombiner`) are permanently gated off
   from live execution. Never activate, wire up, or remove this gate
   without an explicit, direct instruction from Ish given in that exact
   session — not inferred, not implied by a task description. See §6.9.

2. **RAM discipline.** ~10.8GB RAM; this device has crashed from
   concurrent model loads. Before any live test that loads the local
   7B/1.5B/embedding models: run `free -h` and record it verbatim. Never
   run more than one live model-load cycle at a time — a cycle isn't done
   until the model is confirmed unloaded (`ps aux | grep llama-server`
   showing nothing but the grep). Batch test messages into one
   interactive session rather than separate invocations.

3. **Never kill processes by bare name pattern** (`pkill -f <name>`).
   Always track and kill a specific PID your own code spawned. This
   project has been bitten by this exact bug before. Known open
   violations: `NEW-85`, `NEW-99`, `NEW-103` (see Appendix A, M-lane).

4. **Any process-lifecycle change** (daemon start/stop, PID files, kill
   logic, locks, model load/unload, the GUI server's binding/auth)
   requires the code-reviewer subagent's explicit approval before commit,
   regardless of how small the change looks. This category has produced
   this project's worst bugs — including an already-reviewed fix that
   introduced a new self-race. **This rule currently has outstanding debt
   — see §4.4.**

5. **Verification means real, verbatim output** — actual `git diff` text,
   actual timings, actual `free -h` numbers — never a paraphrase or a
   "tests pass" summary.

6. **Correct the record when a claim doesn't hold up.** Downgrade an
   overclaimed finding explicitly in the docs rather than leaving the
   stronger claim standing.

7. **Distinguish "code complete" from "live verified"** in this plan's §4
   and §6 and in `PROJECT_LOG.md`. Never mark something fully done on
   code-complete/mock-tested evidence alone.

8. **Anything found outside a task's scope** — even something small —
   gets logged to `NEW_ISSUES.md` (rated Confirmed or Suspected based on
   actual certainty) and is not silently fixed or silently dropped. If it
   is queue-level work, it also gets a line in this plan's Appendix A.

9. **Update this plan and `PROJECT_LOG.md`** after every completed round,
   with specifics — not "improved" or "done." §4 and Appendix A are the
   status surface; `PROJECT_LOG.md` is the reverse-chronological record.

10. Before creating a new subagent, check `.claude/agents/` for one that
    already fits. Subagent sprawl makes the pipeline harder to reason
    about, not easier.

11. **Keep `install.sh` current.** Any new dependency (pip package,
    `pkg install`, system binary) or setup-step change updates
    `install.sh` in the same task. A fresh clone must be able to run
    `install.sh` once and get a working system.

**Two additional hard invariants carried from the platform work:**

12. **`compute_device_ceiling_bytes()` must never include swap/zram in
    its basis.** Swap softens the *budget* check only. A single model
    that alone exceeds the device's usable physical-RAM ceiling stays
    permanently non-admissible. State this in every code review touching
    the resource gate.

13. **Local-first is the default, not an aspiration.** Cloud (OpenRouter)
    is opt-in fallback. A domain running in cloud-only mode must be
    visibly, deliberately chosen — never silently selected.

---

## 3. Architecture

### 3.1 Mechanism vs. policy — the organizing split

Codey-OS owns **mechanism**: the OS shell, the schema, canonical IDs, the
API, model access arbitration, authentication/roles/permissions, the
audit log, the search index, the task/event queue, hosting the website,
outbound dispatch to the device limb, and backup/maintenance scheduling.

Codey-OS never owns **policy**: what a lead score means, when a follow-up
fires, what a warranty claim requires, which subcontractor gets a job.
Domains own policy, expressed as rules and workflows running over the
Core's data.

This is continuous with how the platform is already built —
`capability_registry`/`plugin_manager` are mechanism today; the plugins
registered through them carry policy.

### 3.2 Platform layer (CCOS) — REAL, mid-build

**Layer A: the OS shell** (`ccos/core/`) — owns discovery, routing,
safety, self-knowledge. Contains no coding-agent intelligence itself.

| Component | Job |
|---|---|
| `capability_registry` | Inventory of everything the system can do — name, implementation, dependencies, status, version, performance |
| `plugin_manager` | Discovers/loads/validates plugins from `ccos/plugins/<category>/<name>/`; `importlib` dynamic loading |
| `tool_router` | Selects the best capability for a task (lexical overlap + learned success/speed/recency score) |
| `agent_orchestrator` | 5-agent deliberation (Planner, Critic, Optimizer, Capability, Safety); weighted voting; **Safety Agent can veto any plan**. Built, not wired to real execution (§6.8) |
| `sandbox` | Isolated execution — no destructive commands, no path escapes, resource limits, timeouts |
| `device_manager` | One-time hardware inventory; gates which capabilities can run here |
| `lifecycle_manager` | task → plan → execute → evaluate → improve → register → store |
| `ccos_memory` | OS-level bookkeeping (skills, workflows, configs, event log, telemetry) — separate from the coding agent's own memory |
| `reflection_engine` / `performance_tracker` / `telemetry_engine` | Post-task evaluation, metrics, drift detection, health scoring |
| `goal_engine` / `project_engine` | Improvement goals → persistent multi-session projects. **Gated (rule 1)** |
| `capability_optimizer` / `skill_recombiner` / `auto_improvement_loop` | Self-improvement. **Gated (rule 1)** |

**Layer B: capabilities** — the coding agent's real work (`core/`,
`tools/`, `main.py`), wrapped as registered capabilities rather than
directly-called modules.

Capabilities already CCOS-native: `system_info`, `camera_capture`,
`tts_speech`, `daemon_control`, `observability`, `error_recovery`,
`peer_escalation`.

Capabilities still needing wrapping: the coding agent itself (§6.8 item
4.3 — the big one), plan-then-execute mode, persistent daemon, recursive
self-refinement, git integration, voice, static analysis, thermal
throttling, fine-tuning export, peer CLI escalation.

Capabilities complete but disconnected: `core/recovery.py` (needs a call
site in `agent.py`'s tool-failure path) and `core/observability.py`
(wired to `/status` as of 4.1 sub-task A).

**Explicit platform non-goals** (carried from the vision doc §6, still
binding): not a cloud service; not silently dropping working
functionality during unification; not activating autonomous
self-modification by default; not letting GUI and TUI drift out of sync
(both read one dashboard data layer); not going back to fragmented entry
points (`codey-start`/`codey-stop` are the surface); not maintaining two
implementations of the same job without a stated reason; not treating
§3.4's planned architecture as already built; **not** building a general
shared-memory grant across capability domains — only an explicit
publish/read task-context blackboard crosses domain lines.

### 3.3 Business layer — the Core

**The Core is four layers.** Field-level detail for each is in
Appendix C (Ish's own CRM module breakdown, kept verbatim so field lists
are edited in exactly one place).

- **Core schema / entities** — Customer, Lead, Opportunity, Project/Job,
  Estimate, Proposal/Contract, Document, Invoice/Payment, Employee/User.
  Canonical IDs that everything else references (Finance holds
  `customer_id = 1842`, never its own copy).
- **Core services** (owned by Codey-OS, cross-cutting, no domain owns
  one) — Communication History, Tasks/Follow-ups, Calendar, Global
  Search, Audit Log. **Communication History and Audit Log are
  day-one-or-never**: append-only, cannot be backfilled.
- **Domain behavior** — business rules over the schema, using the
  services: Automated Workflows, Marketing, Customer Service,
  Reporting/Dashboard; CRM/Sales, Operations, Finance/Bookkeeping,
  Compliance, HR, Procurement each own their slice of rules, none
  duplicating schema data.
- **Surfaces & integrations** — three clients (§3.5), plus Gmail,
  calendars, ad platforms, payment processors, accounting software,
  e-signature.

Status: **DESIGNED. None of it exists today.**

### 3.4 One brain, two limbs — not three peer agents

Codey-OS is one brain with two limbs that differ by **what they can
physically reach, not by rank** (Revision 5 correction — earlier drafts'
"three runtime agents" framing is retired).

- **The voice/inbox limb** — Gmail/IMAP-SMTP and Google Voice
  SMS-over-email. IMAP IDLE holds a live protocol connection open and
  works with the screen off; nothing about that needs a visible app.
- **The screen/hands limb** — everything that only exists behind a
  third-party app's UI (Messenger, WhatsApp, social posting) via the
  Android accessibility tree, plus device-native one-shot actions
  (calls, SMS, alarms), plus scheduled commands dispatched from
  Codey-OS. Also renders a dashboard of Core data it never owns a copy
  of beyond client-side caching.

**These cannot be collapsed into one process.** Codey-OS's Python
process has no access to Android's accessibility APIs; a Flutter/Dart
app isn't built for IMAP IDLE or SMTP. The three-process shape is a
consequence of what each runtime can physically talk to, not an accident
of history.

**Rewriting the comms limb into Codey-OS's Python process was considered
and rejected** for this build: ~120KB of already-debugged IMAP-reconnect
handling, Google-Voice-SMS-as-email parsing, deterministic date parsing,
and NL command interpretation, in daily production use, against a
Jan-1 date that already carries every domain plus the full portal. It's
little gain specifically because `core/resource_gate.py` already
arbitrates by `model_id` across multiple named roles — folding those
model calls in-process would add one more `model_id` to a gate already
built for several, not simplify anything.

**The repos** (Revision 6, settled):

| Repo | Status | Role |
|---|---|---|
| `~/Aigentik-CLI` | REAL, untouched | Stays a standalone general-purpose open-source product with its own users. **Not modified by this project.** |
| `Codey-Aigentik` (new fork) | DESIGNED, not created | "Codey-OS's voice and inbox." Git fork of Aigentik-CLI carrying all Codey-OS integration (drop the local JSON store, write through to the Core). Upstream fixes pulled via `git fetch upstream`. |
| `~/private-agent` | REAL, untouched | Stays a standalone open-source product (itself already a fork of `orailnoor/private-agent`). **Not modified by this project.** |
| `Private-Codey-Agent` (new fork) | DESIGNED, not created | "Codey-OS's eyes, hands, ears, and voice." Git fork carrying the dashboard, scheduled-command handling, and the narrowing toward pure executor+client. |
| `~/restoricon` | REAL (static site) | Becomes the phone-hosted customer/staff-facing surface (§3.5). `llms-full.txt` is ready-made seed content for the Core's business-profile record. |

**Named, accepted cost:** forking doesn't eliminate drift, it gives git
tooling to manage it. A fix in a fork that also matters to the public
repo's users has to be ported back by hand, since the public repos won't
track the forks as upstream. This is an ongoing two-codebase cost on
both limbs, accepted deliberately.

**Supervision:** Codey-OS supervises the `Codey-Aigentik` fork's process
as `agent_type: external_process` (the path
`docs/agent-plugin-blueprint.md` §4.2 already designed). That needs
process-supervision plumbing in `ccos/core/plugin_manager.py` that does
not exist yet — real, scoped work (§6.8), not a rewrite.
`Private-Codey-Agent`, being a separate Android app with no equivalent
local-supervision path, keeps its own process lifecycle but is the same
kind of limb conceptually.

**Both limbs write through to the Core and never keep their own store.**
From the Core's point of view, "who handled this interaction" is metadata
on one shared Communication History record, not two separate histories.

### 3.5 Three client surfaces, one API, one auth system

Owner/staff via the device limb's dashboard, staff/admin via the
website's authenticated admin page, and customers via the website's
customer portal are **three clients of the same Core API, distinguished
by role, not by separate implementations.** This is the load-bearing
simplification that keeps three surfaces from tripling the build: one
data layer, one API, one auth/permission system, written once and
consumed the same way, filtered by role.

**Because a customer-facing login exists, roles and permissions are not
deferrable.** The moment a customer can log in and see project data, a
bug in that boundary means one customer sees another's contract. There
is no "hidden page" shortcut: an unauthenticated admin URL that is merely
unlinked is not a security boundary — it is the same login system with a
different role. This forces auth/roles into Jan-1 scope.

### 3.6 Deployment: phone first, portability as a discipline

**Confirmed: everything runs on one phone to start** — the Core, the API,
and the website. Migrating later to Firebase or a larger server is the
acknowledged future direction, **not decided and not designed**.

The one commitment held while building: **a plain HTTP/API boundary, even
when both sides run on the same phone.** No shared-memory shortcuts
between the website's backend code and Codey-OS's Python internals. That
is what keeps a future hardware move from being a rewrite. It is a design
discipline, not a project.

Also confirmed and explicitly deferred: **scheduled maintenance windows
and periodic backups to another storage location.** Real requirements,
"to be figured out" per Ish — named here so they aren't forgotten.

### 3.7 The shared model layer and the Model Orchestrator

One shared local model server, used by Codey-OS and both limbs, with
Codey-OS tracking access so nothing gets crossed. Three distinct problems
inside that:

- **Concurrent requests** — likely solvable via `llama-server`'s
  slot/`--parallel` handling; **unverified — no such flag is set anywhere
  Codey-OS launches `llama-server` today.** Test this directly before
  building anything more elaborate.
- **Model residency** — ~10.8GB cannot hold every model simultaneously.
  The resource gate arbitrates which model is loaded and who may trigger
  a swap. This is the work in §6.2.
- **Adoption vs. leasing** — `core/loader_v2.py` decides "is my coder
  server already running?" by probing port 8080. A shared model server
  needs an explicit lease/registry, not a port-occupancy guess that
  `core/embed_server.py`'s `_kill_port_occupant()` can act on. Tracked as
  the lease/registry item in §6.2 (and by `NEW-104`/`NEW-144`/`NEW-149`).

**The Model Orchestrator** (vision §11, DESIGNED, not built) is the layer
*above* the gate: models are **ephemeral workers** — loaded for a job,
passing a small structured record onward, unloaded when resources are
better used elsewhere. Accessibility services, shell, filesystem, vision,
browser are **tools, not models**; many steps need no model at all.
Admission ("can we") and scheduling ("should we, right now, for this
task") are two different questions: the gate answers the first, the
orchestrator the second. Its decision logic is **deterministic-first** —
ordinary software, not a model call per routing decision.

Its named future inputs, none built: a fuller resource profile (GPU/NPU,
battery/charging, model load time, estimated inference cost); adaptive
`n_ctx` and CPU allocation computed per load attempt rather than a fixed
global; per-domain approved model lists spanning largest→medium→smallest;
confidence-gated escalation up that list; and OpenRouter as an
orchestrator-selectable tier per domain (per-domain enable/disable,
per-domain model choice, three modes: cloud-only / local-only /
automatic, with automatic distinguishing "no viable local model" from
"device can't run one right now").

**The open fork, still Ish's call:** can one model serve coding tasks,
customer-facing prose, and on-screen reasoning well enough to avoid swap
scheduling entirely? Test the concurrency question first, then decide.

---

## 4. Where things actually stand (2026-08-21)

This section is the current-state snapshot. Keep it accurate; it is the
first thing a new session reads after the rules.

### 4.1 Built and live-verified

- **Unified entry points** `codey-start` / `codey-stop` — replaced the
  fragmented `codey3`/`codeyd3` scripts; `ccos_main.py` and
  `gui/start.sh` removed as dead code.
- **CCOS Phases 1–3** (capability wrapping pilot, remaining capability
  migration, entry-point unification) — complete per the archived
  `PROJECT_PLAN.md`.
- **Resource gate core path** (`core/resource_gate.py`): admission →
  load → CLI-recovery, live-confirmed round 18 (2026-08-09, commit
  `aa18b7a`) at a substitute model and `n_ctx=2048`, including a real
  transient denial → daemon slot release → retry → real inference cycle.
- **Swap-assisted admission** at `n_ctx=16384` (2026-08-11, 7.4a sub-task
  E): real gate call, 11.21s spawn, stable ~6.58–6.96GiB RSS, a real
  8.25s inference request with coherent output, `SwapFree` staying >12GiB
  above the device's slmk kill floor throughout, clean PID-tracked
  teardown.
- **Single-model load at the real production `n_ctx=32768`** (2026-08-11,
  7.4a sub-task G case (a)) — full pass with the 10GiB
  `MAX_SWAP_ASSIST_BYTES`. **Single-model only — the same run's
  concurrent case (b) failed; see §4.3.**
- **Daemon control redesign (4.1) sub-tasks C and D** — gated queue
  dispatch (interactive TUI/GUI session defers background dispatch) and
  the autonomous thermal shutdown tripwire, both live-verified 2026-08-10
  (commit `96b6ea1`).
- **20+ audit-remediation rounds** (NEW-1 … NEW-20 and the prompt
  rounds), including the `NEW-30` read-before-patch fix — decisive live
  A/B: 3/3 read-before-patch with the fix, 0/3 without.

### 4.2 Built, approved, not live-verified

- 7.4 sub-tasks 1–5 (gate module, slot-aware loaders, daemon outcome
  surface, `release_model_slot` socket command, CLI gate recovery).
- 7.4a sub-tasks A/B/C1/C2/D (swap signal sourcing, swap-assisted
  headroom function, the `MAX_CONCURRENT_MODEL_BUDGET_BYTES` = 8.90GiB
  cumulative ceiling, the swap-assist branch in `can_admit()`, the
  consistency pass across `would_model_fit()`/`can_dispatch_task()`).
- 7.4a sub-task F (`MAX_SWAP_ASSIST_BYTES` raised to 10GiB) — partially
  live-covered by G.
- 7.3 sub-tasks A–D (shared signal-scoring helper, `core/model_tiers.py`,
  `classify_tier()` wired **log-only** into `planner_service.get_plan()`,
  test coverage). Nothing dispatches on a tier decision yet.
- 4.1 sub-tasks A, B, E.

### 4.3 The one honest platform gap

**Concurrent primary + planner at `n_ctx=32768` does not work on this
device.** 7.4a sub-task G case (b) reproduced `NEW-14`'s swap-distress
shape live with the 10GiB swap-assist cap in place (`NEW-141`). The
`NEW-140` low-swap-headroom single-model scenario was deferred, not
safely reproduced. This is what 7.4b's three-part model-lifecycle policy
(embed always resident; planner capped at 8192; coder context dynamic
except in interactive use) exists to address.

Related, still open: `NEW-137` (production 32768 never reached the
swap-assist band at any observed live headroom during sub-task E),
`NEW-138` (an unexplained ~1.56GiB anon-RSS gap), `NEW-139` (`--mmap`
makes quantized-weight zram compression structurally unmeasurable),
`NEW-143` (the production 7B's cost estimate sits ~137MiB under the
hard-reject ceiling — a thin margin, not a comfortable one).

### 4.4 Outstanding process debt — read before starting Phase 1 work

**Rule 4 has live debt.** `NEW-151` recorded a self-found process
violation: commit `5687dcf` swept in two already-implemented,
rule-4-category process-lifecycle changes (7.4b sub-tasks A and C)
without the mandatory `code-reviewer` pass. A retroactive review found a
Critical gap (`NEW-152`, sticky `_ever_loaded` reopening `NEW-145` after
adoption), which was then fixed in commit `6528446` — but **that fix is
itself code-complete only, not code-reviewer-approved and not
live-verified.** `NEW-145`, `NEW-149`, and `NEW-155` stay open.

**Concretely, before any new 7.4b work:**
1. A real `code-reviewer` pass on 7.4b sub-task A's diff
   (`EmbedServer.is_healthy()`, `core/inference.py:_start_server()`).
2. A real `code-reviewer` pass on the `NEW-152` fix
   (`_ever_spawned`/`was_ever_spawned()` in `core/loader_v2.py`,
   `_watchdog_check_model()` in `core/daemon.py`).
3. `live-verifier` on both, under the real `codey-start` entry point —
   `NEW-145` was only ever found under the real entry point, never under
   a synthetic harness.

**Working tree state:** clean as of 2026-08-21 (only this plan's own new
files untracked). Notes in the archived `TODO.md` saying 7.4a/7.4b work
is "uncommitted as of this writing" are **stale** — that work is
committed (`5687dcf`, `6528446` and predecessors).

**Test suite:** 742 passed, 1 skipped as of 2026-08-13. Known expected
noise: `tests/test_new19_patch_failed_repeat_escalation.py` fails or
hangs whenever the working tree is dirty (`NEW-110`/`NEW-150`) — that is
a test-isolation gap, not a regression.

### 4.5 Business layer

**Nothing is built.** `~/restoricon` is a static marketing site with
`mailto:` lead forms. No Core, no API, no auth, no portal, no forks
created. Everything in §3.3–§3.6 is DESIGNED.

---

## 5. The device, stated once

Numbers that keep getting re-derived. Re-measure before relying on them;
they drift sample to sample.

- `MemTotal` ~10.82GiB. `MemAvailable` at idle: ~5.3–6.5GiB. Highest
  ever recorded in this project's live-test history: ~7.6GiB.
- Swap: zram, `SwapTotal` ~16.0GiB (raised by Ish from ~12GiB during the
  7.4a work). **`MemAvailable` structurally excludes swap** — adding swap
  does not raise it.
- Samsung low-memory-killer floor: `ro.slmk.swap_free_low_percentage` =
  `10`, i.e. `SwapFree` below 10% of `SwapTotal` (~1.6GiB today) triggers
  kills. Any swap-budget check must stay well above this.
- Android/OS memory is **structurally invisible from Termux** (sandboxed
  app UID; `/proc/swaps` permission-denied; no `swapon`/`dumpsys`). The
  ~5GiB of "used" at idle is mostly not attributable to anything this
  project controls or can see.
- `/proc/stat`, `/proc/uptime`, `/proc/loadavg` are **permission-denied**
  here (`NEW-108`) — CPU% is unmeasurable without `psutil` (not
  installed). Every gate/dispatch decision treats "CPU unmeasurable" as
  "don't refuse on it alone."
- Model costs at `n_ctx=32768`, computed from the real on-disk files:
  7B coder = 6.361GiB; 1.5B planner = 2.166GiB; embed = ~0.328GiB (floor
  estimate — no computable KV term, and it actually launches at `-c 2048`
  which is the real GGUF context length for that model). Raw sum
  ~8.855GiB → `MAX_CONCURRENT_MODEL_BUDGET_BYTES` = **8.90GiB**.
- `MAX_SWAP_ASSIST_BYTES` = **10.00GiB**; `REQUIRED_HEADROOM_FACTOR` =
  1.25; `DEVICE_CEILING_USABLE_FRACTION` = 0.60 (→ device ceiling
  ~6.49GiB).

---

## 6. The plan

Two tracks run in parallel, plus standing lanes that never close.
**Track A (platform)** unblocks anything needing a model. **Track B
(business)** is the Jan-1 deliverable. They intersect at exactly two
points, named below.

### 6.0 What this merge collapsed

Recorded so nobody re-splits them:

- The old `Codey-Restoricon-OS.md` §8 step 2 ("the shared model layer")
  **is** the old `TODO.md` Phase 1 (7.4 / 7.4a / 7.4b) plus 7.3's tier
  work plus the lease/registry replacing port-probe adoption. One item:
  **§6.2**.
- The old §8 step 8 ("formal CCOS plugin registration of the limbs as
  `agent_type: external_process`") **is** the old Phase 2's 9.3/9.4 plus
  Phase 3's 9.2. One item: **§6.8**.
- The old §8 step 3 ("Aigentik's write-through migration") is a Track B
  item that depends on §6.3's Core existing, not on the model layer. It
  is sequenced accordingly, not where the old numbering put it.
- `PROJECT_PLAN.md`'s "Phase 5a/5b/5c/5d/5e/5f" and `WORK_QUEUE.md`'s
  "Track 3 items 1–8" were two names for the same eight platform items.
  Only the vision-doc numbering (7.4, 7.3, 4.3, 7.5, 4.5, 4.6, 4.7)
  survives; the other two naming schemes are retired.

### 6.1 Standing lanes (never "done", interleave anytime)

**M-lane — maintenance and bug fixes.** Every `U.x` item in Appendix A
that is not gated by a phase. No dependency on anything below. Highest
value first: the rule-3 `pkill` violations (`U.30`/`U.32`, same files,
do them together), the gate accounting gaps (`U.33`/`U.34`), and the
7B-agent failure spiral (`U.11`/`NEW-60`).

**D-lane — documentation.** `docs/architecture.md` rewrite (best done
after §6.8's 4.3 lands), `docs/commands.md` gaps, `docs/TODO2.md`
re-verification, README docs-table discoverability.

**F-lane — findings discipline.** Rule 8. Every out-of-scope discovery
goes to `NEW_ISSUES.md`; queue-level ones also get an Appendix A line.

### 6.2 Track A / Phase A1 — Finish the model foundation

**Why first:** nothing that loads a model is safe until this is real, and
`NEW-141` proves the current state genuinely fails on this device for the
concurrent case. Also unblocks §6.5's AI-assisted domain behavior.

**Blocked-by:** §4.4's review debt. Clear that first.

| Item | State | What's left |
|---|---|---|
| **7.4** resource gate + slot-aware loader | 5/5 sub-tasks approved; core path live-verified | The scoped daemon-only live pass at production `n_ctx=32768` with `CODEY_N_CTX` unset (full step-by-step in the archived `TODO.md` 7.4). Largely superseded in practice by 7.4a G case (a) — re-scope rather than re-run verbatim. |
| **7.4a** swap-aware budget | A/B/C1/C2/D/F built and approved; E and G run | `NEW-140` scenario 3 (low-swap-headroom single model) still not safely reproduced; `NEW-135`/`NEW-136` (no `reserved_bytes` deduction on swap-assist; `admitted_via_swap` not persisted to the slot) unfixed |
| **7.4b** model lifecycle policy | Ish's three decisions confirmed | **A**: embed always resident — implementation landed, needs its real review (§4.4). **B**: planner ceiling 8192 — confirmed by Ish, ready for implementer, not started. **C**: coder interactive-vs-daemon context branching — landed + `NEW-152` fix, needs review + live-verify. **D**: docs-only revisit of the 8.90GiB ceiling under the new policy. |
| **Lease/registry** | Not started | Replace port-probe adoption with an explicit lease. Absorbs `NEW-104` (slots key to caller PID, not the spawned child), `NEW-144`/`NEW-146` (kill-and-replace a healthy occupant), `NEW-149` (reuse branch adopts an under-provisioned server). **This is the actual prerequisite for a shared model server across three processes** — do not treat it as a cleanup item. |
| **Concurrency test** | Not started | Does `llama-server`'s slot/`--parallel` handling let one server serve Codey-OS and both limbs? No flag is set anywhere today. **Test this before designing anything.** Its answer decides the one-model-vs-swap-scheduling fork (§8 Q3). |

**Exit criteria:** a real production-config load through the gate,
live-verified with verbatim numbers; concurrent primary+planner either
working under the 7.4b policy or explicitly documented as
not-supported-by-design; the lease/registry replacing port probing; and
the concurrency question answered with real output.

### 6.3 Track B / Phase B1 — The Core's foundation

**Can start immediately, in parallel with A1** — schema, API, and auth
are ordinary Python/data work with no model dependency. This is the
single most important sequencing insight of this merge: **do not wait for
the model layer to start the Core.**

1. **Schema and canonical IDs** — the nine entities in §3.3, field-level
   per Appendix C. One store, canonical IDs, no domain-local copies.
2. **The API** — a plain HTTP boundary (§3.6). Every surface and every
   limb goes through it, including code running on the same phone.
3. **Auth, roles, permissions** — not deferrable (§3.5). The role ladder
   from Appendix C §16: Admin → Manager → Sales → Project Manager →
   Technician → AI Agent. Customer is a role too, with visibility scoped
   to its own records.
4. **The two day-one-or-never services** — Communication History and
   Audit Log. Append-only. Every action by a human or an agent lands in
   the audit log with actor and timestamp. **If these are not built
   day one, their history is permanently lost** — that is the entire
   reason they are in this phase and not a later one.

**Rule-4 note:** the API's binding and auth are explicitly rule-4
territory (same category as the GUI server's). Mandatory code-reviewer
pass.

**Exit criteria:** a running local API, an authenticated request from a
second process on the device returning correctly role-filtered data, and
a Communication History + Audit Log record written by both a human action
and an agent action.

### 6.4 Track B / Phase B2 — The voice/inbox limb writes through

**Depends on:** B1 (needs the Core to write to). Independent of A1 except
where model calls are involved.

1. Create the `Codey-Aigentik` fork with `Aigentik-CLI` as upstream.
2. Migrate `data/*.json` (contacts, calendar, rules, profile) into the
   Core's schema. **This is when CRM/Sales gets its first real data** —
   the existing contacts are the seed.
3. Replace local writes with Core API write-through. It keeps exactly one
   job: being the execution surface for Gmail/SMTP-IMAP and Google Voice
   SMS-over-email.
4. Point its model calls at the shared model layer (config change once
   A1's lease/registry exists).

**Exit criteria:** the fork runs with no local data store, an inbound
email produces a Communication History record in the Core, and an
owner-command roundtrip works end to end.

### 6.5 Track B / Phase B3 — CRM/Sales and Operations

**Depends on:** B1; B2 for real seed data; A1 for anything AI-assisted
(lead scoring, drafted follow-ups).

The two domains with the most existing groundwork and the ones every
other domain implicitly assumes exist — Finance needs jobs to invoice
against, Marketing needs leads to report on, Compliance needs
subcontractor records to monitor.

- **CRM/Sales**: Customer/Contact Management, Lead Management, Sales
  Pipeline (New Lead → Contacted → Appointment Set → Estimate → Proposal
  Sent → Negotiating → Won/Lost), Tasks & Follow-ups.
- **Operations**: Projects/Jobs, Calendar/Scheduling, Estimates/Quotes,
  Proposals/Contracts, Documents.
- The first Automated Workflows on top of them (Appendix C §13's four
  worked examples are the acceptance cases).

### 6.6 Track B / Phase B4 — The phone-hosted website, three surfaces

**Depends on:** B1 (API + auth), B3 (data worth showing).

1. The existing public marketing site, now served from the phone.
2. The **staff/admin surface** — a real authenticated admin page, not a
   hidden URL.
3. The **customer portal** — project status, appointments, estimates,
   contracts, invoices, payments, messages, documents, photos, change
   orders, warranty info, approvals, signatures (Appendix C §12). Full
   document/signature/financial surface, not a view-only stub.
4. The **device-limb dashboard** as the third client of the same API —
   business calendar, financial summary, contacts, all fetched, none
   owned locally beyond caching.

**This is the highest-risk security surface in the whole plan.** One
boundary bug means one customer sees another's contract. Mandatory
code-reviewer pass on every auth/permission change, and a dedicated
authorization test suite — not just "it works when I log in."

### 6.7 Track B / Phase B5 — The remaining domains, then the device limb

**B5a — the remaining domains.** Finance/Bookkeeping (invoicing, payment
tracking, project financial summary — track money, don't rebuild an
accounting system; connect a real one later), Marketing/Lead-Gen
(campaigns, segmentation, ad-platform integrations, review requests),
Compliance (expiration monitoring and alerting), HR (onboarding,
recruiting, documents, PTO), Customer Service (ticketing, warranty
claims, satisfaction), Procurement (vendors, POs). These can build in
parallel with each other once B1 exists — none depends on another the
way B3's domains are depended on. Each is real scoped work: its own
schema on top of §3.3's shared entities, plus its own rules.

Plus the cross-cutting pieces they all feed: **Global Search** (one query
across customers → leads → jobs → estimates → contracts → emails → SMS →
appointments → payments → documents → tasks, a first-class feature) and
**Reporting/Dashboard** (Sales, Operations, Financial, Marketing views).

**B5b — the screen/hands limb.** Create the `Private-Codey-Agent` fork;
build third-party-app automation (Messenger, WhatsApp, social posting)
via the accessibility tree; and build **the Core→device dispatch
mechanism**, which does not exist in any repo today. The device app
already maintains a background Telegram Bot API polling connection for
remote control — a plausible existing transport to reuse rather than
invent a new one, **but the protocol is not designed anywhere yet** (§8
Q2). Sequenced last because it has the most net-new mechanism to invent,
not because it matters least.

### 6.8 Track A / Phase A2 — Coding-domain architecture rollout

Runs in parallel with Track B once A1 is real. This is the platform's own
long-planned rollout (vision §7.6 steps 2–6 plus §9.7), unchanged in
order.

| Item | Depends on | Note |
|---|---|---|
| **7.3 sub-task E** — actually dispatch on the tier decision | A1 | A–D are built and log-only today. `NEW-126` (thresholds resolve to "large" for nearly everything) and the missing remote-tier path must be addressed here. |
| **4.3** — wrap `core/agent.py` as a real CCOS capability | A1 | Migrate **both** existing call paths (`main.py` for CLI/GUI, `core/task_executor.py` for the daemon) onto one boundary — not a third path alongside them. The wrapper owns its own permission surface (`confirm_shell`/`confirm_write`) explicitly rather than inheriting the caller's. Also where recursive self-refinement gets wrapped. |
| **7.5** — in-flight context passing + task-context blackboard | 4.3 | `plugin_manager.call_capability` gets a threaded context argument (today a step's output is silently discarded); plus a scoped task-context table for durable cross-step handoffs. **Not** a general shared-memory grant, **not** a repurposing of `ccos_memory`. Per vision §11.2 the threaded content is a compact structured record, not a conversation dump. |
| **4.5** — peer-CLI escalation redesign | 4.1's queue, 7.5's blackboard | Daemon pulls an item needing escalation off the main queue, parks it on a review list, notifies the user, keeps working. 100% design-only today. |
| **4.6** — wire `agent_orchestrator` to real execution | 4.3 | Cheap (heuristic, not model-backed) but **the Safety Agent's veto becomes live against real actions for the first time** — a behavior change to flag, not just wiring. |
| **4.7** — multi-domain request splitting | 4.3, 7.5, 4.6 | First point where capability-as-plugin, context passing, and the blackboard compose. |
| **9.3** — manifest schema extension | none (design-only) | `agent_type`, `model_tiers`, `resource_footprint`, `event_triggers`, `permissions`, `data_store`. Proposed in `docs/agent-plugin-blueprint.md` §3; read by no code today. Design only — do not implement against the registry yet. |
| **9.4** — limb-integration plan | 9.3 | Produce an actual integration plan (design level worked through in blueprint §4) before any code is written against it. |
| **9.2** — generalize the gate into a scheduler/resource-bus | A1 | Arbitrate across multiple agent processes, not just Codey-OS's daemon; queue work when resources aren't available. Must handle push-driven agents (IMAP-IDLE-triggered) as well as pull-driven ones — **open design question, unanswered.** |
| **`external_process` registration** | 9.2, 9.3, 9.4 | Formal CCOS registration of both limbs. Independent of whether they are Core clients (they can and should be, well before this). |

**The one dependency this plan cannot promise a date for:** the
`external_process` registration is gated on the platform's own gate work
being fully live-verified. If that isn't done by the time everything else
is ready, **this step alone may slip past Jan 1 without blocking anything
the business needs day to day.** Flagged so the dependency is visible,
not to soften the date.

**11.x — the Model Orchestrator** (§3.7) stays **parked as a whole**
until a domain agent that actually needs it is scoped through the normal
pipeline. `core/resource_gate.py`'s existing admission logic is unchanged
by it — it names the layer *above* the gate, not a revision to what's
built.

### 6.9 Parked — do not start without Ish's explicit sign-off

**P.1 — self-improvement activation** (`auto_improvement_loop`,
`capability_optimizer`, `skill_recombiner`, `goal_engine`). Gated by rule
1. Do not start until: everything above is stable, a meaningful period of
observed real-task operation through the sandbox/safety-veto path has
elapsed, **and** Ish gives explicit, direct, in-session sign-off — not
inferred from this plan reaching its end.

When that time comes: review the engines' behavior in a controlled test
(not live); decide what compound-skill creation should require before
`skill_recombiner` may register something automatically; decide whether
`goal_engine`'s generated goals need approval before entering the planner
queue. Only after sign-off, wire into the live path.

Historical note: three pre-existing `skill_recombiner` *outputs* under
`ccos/plugins/compound/` were live and agent-callable despite the engine
never running — the gate on the engine didn't stop `plugin_manager` from
auto-loading its output. All three were permanently removed on Ish's
instruction (`NEW-34`). That was an output cleanup, not an activation
decision; the engine gate is untouched.

---

## 7. Risks

Stated once, honestly, and not argued with. The date is settled (§1.3);
these are the things that could go wrong against it.

1. **The platform's foundation is not live-proven at production config.**
   Concurrent primary+planner at `n_ctx=32768` reproduces swap distress
   on this device (`NEW-141`), and the production 7B's cost sits ~137MiB
   under the hard-reject ceiling (`NEW-143`). 7.4b's policy is the
   intended answer and is only partly built and partly unreviewed. Every
   AI-assisted business behavior sits downstream of this.
2. **Full scope, four months, solo, on a phone.** Eight domains, a Core,
   an API, an auth system, three surfaces, two forks, and a dispatch
   protocol that doesn't exist yet. The mitigation in this plan is
   §3.5's one-API/one-auth simplification and starting Track B
   immediately rather than serializing behind Track A.
3. **The auth boundary.** A customer portal makes an authorization bug a
   data breach between real customers. Treated as rule-4 category
   throughout §6.6.
4. **Two forks to maintain.** Accepted deliberately (§3.4), but it is a
   real ongoing cost, not a one-time one.
5. **Process debt compounds.** `NEW-151` is the shape of the failure: a
   fix that skips the review gate produces a Critical follow-on
   (`NEW-152`) that then also ships unreviewed. §4.4 must be cleared
   before Phase A1 continues.
6. **Device opacity.** CPU% is unmeasurable here; Android's own memory
   use is invisible from Termux; `MemAvailable` peaks below what the
   shipped default needs. Some decisions will have to be made on partial
   signals, and should say so rather than implying certainty.

---

## 8. Open decisions awaiting Ish

Numbered for reference. Nothing here is guessed at in this document.

1. **`n_ctx` production default.** The shipped `32768` needs ~7.95GiB of
   `MemAvailable` to pass the gate's plain budget check — a bar this
   device's live-test history has never reached (peak ~7.6GiB). Swap
   assist now covers the single-model case, but should the production
   default itself come down (with `CODEY_N_CTX` staying the override)?
   Product decision, not implementation detail. Conditions 7.3's tier
   thresholds and what "closed" means for the gate work.
2. **The Core→device dispatch mechanism.** Reuse the existing Telegram
   Bot API channel the device app already polls, or build something
   Codey-OS-native? Not designed anywhere.
3. **One model vs. swap scheduling.** Can one model serve coding,
   customer-facing prose, and on-screen reasoning well enough to avoid
   swap scheduling entirely? Test the `llama-server` concurrency question
   first (§6.2), then decide.
4. **Deployment migration off-phone.** Firebase, a bigger server, or
   something else. Explicitly not decided; revisit after the
   phone-hosted version is real.
5. **Backup and maintenance windows.** Real requirements, explicitly
   deferred, "to be figured out."
6. **`NEW-9`'s residual atfork race.** Already escalated twice; each
   attempt an improvement, neither a full close. The question is
   accept-residual-risk vs. a third attempt with a genuinely new angle —
   **not** a normal fix task to pick up without that call (`U.8`).
7. **`NEW-69` / interactive-CLI direct loads.** A naive fix breaks normal
   CLI use whenever the daemon has a planner loaded; it needs real
   cross-process arbitration. Get Ish's call on sequencing relative to
   the gate work (`U.9`).
8. **Attribution-logging coverage.** Extend `core/recursive.py`'s
   attribution logging to `core/agent.py`'s separate plain-`infer()`
   branch as new work, or leave it as a documented accepted gap
   (`U.10`)?

---

## 9. Document map

**Authoritative:**
- **`CODEY_MASTER_PLAN.md`** (this file) — the plan, the rules, the
  architecture, the current state, the open register. Start here.
- `CLAUDE.md` — agent operating instructions; points here.
- `README.md` — user-facing; points here.

**Live append-only ledgers, owned by this plan** (deliberately *not*
archived — archiving them would break rules 8 and 9 immediately, since
both are written to on every round):
- **`NEW_ISSUES.md`** — the findings ledger (rule 8). NEW-1 … NEW-155
  today. Per-issue status is authoritative *there*; this merge did not
  re-adjudicate 155 statuses, and Appendix B says so plainly rather than
  guessing.
- **`PROJECT_LOG.md`** — reverse-chronological record of every round
  (rules 7 and 9). Add a new entry at the top after every meaningful
  change, with specifics and verbatim verification output.

**Still live, unchanged by this merge:**
- `LIVE_TEST_QUEUE.md` — model-load verification steps deferred for Ish
  to run himself. Not superseded; this plan references it.
- `docs/agent-plugin-blueprint.md` — the `agent_type`/`model_tiers`/
  `resource_footprint` manifest design and the limb-integration
  worked example. Still the design source for §6.8's 9.3/9.4.
- `PENDING_ISH_DECISIONS.md` — **fully resolved, no open items**; kept as
  the record of four capability-wrapping decisions (fine-tuning/model
  swapping: manual-only indefinitely; daemon control: wrapped and
  redesigned, closed 2026-08-10; peer-CLI escalation: wrap later with a
  redesigned async consent mechanism — that design is §6.8's item 4.5;
  `core/observability.py`: folded into the daemon-control work).
- `CHANGELOG.md`, `docs/*` (installation, commands, configuration,
  architecture, security, fine-tuning, pipeline, knowledge-base,
  troubleshooting, version-history), `Codey-OS-audit.md`,
  `MODEL_COMPARISON.md`, `PRIVACY.md`.

**Archived — evidence only, never plan from these:**
- `docs/archive/CODEY_OS_MASTER_VISION.md`
- `docs/archive/Codey-Restoricon-OS.md`
- `docs/archive/TODO.md`
- `docs/archive/WORK_QUEUE.md`
- `docs/archive/PROJECT_PLAN.md`
- `docs/archive/AUDIT_REPORT.md` (archived earlier, June-2026 pre-CCOS era)

They hold the full evidence trail — verbatim live-test output, byte-exact
gate decisions, review histories, the reasoning behind every scoped
sub-task. When Appendix A's one-line status isn't enough, that's where
the "why" is.

---

## 10. How work gets done

`project-architect` is the entry point for any new piece of work: read
this plan first, then decide which specialist the task actually needs.

- **CCOS capability/plugin work** (wrapping a function as a capability,
  writing/auditing a `manifest.json`, deciding whether something is safe
  to expose to agent-driven planning, deciding which internal agent —
  Planner, Critic, Optimizer, Capability, Safety — should call a given
  capability): scope with **agent-tool-designer** first, then hand to
  implementer.
- **Qwen prompt work** (`prompts/system_prompt.py`,
  `prompts/layered_prompt.py`, `prompts/critique_prompts.py`,
  `core/plannd.py`'s `PLANNER_PROMPT` — tuning or debugging how the local
  7B agent or 1.5B planner follows instructions): scope with
  **prompt-engineer** first, then implementer if a separate
  implementation pass is needed.
- **General coding work** goes straight to **implementer**.
- **Every task** goes through **code-reviewer** before commit — mandatory
  for process control, daemon/kill logic, model load/unload, and security
  (including the new Core API's binding/auth); a lighter pass otherwise.
  Loop back to whoever built it on rejection.
- **live-verifier** confirms on-device when a change needs real
  confirmation — after code-reviewer approves, before the round is done.
- **code-hygiene-auditor** runs as a periodic or explicitly requested
  read-only pass, separate from the per-task chain. Its findings go to
  project-architect and get scoped like any other finding.
- project-architect updates §4, Appendix A, and `PROJECT_LOG.md` once a
  round is fully done.

No shortcuts for changes that look small or obvious — that assumption is
exactly what caused this project's worst bugs, and `NEW-151` is the most
recent example.

**Stop and escalate to Ish instead of proceeding when:** code-reviewer
rejects the same fix twice without converging; live-verifier shows the
original symptom isn't resolved or shows a new regression; the work would
touch this plan's own architecture or the gated self-improvement
mechanisms; repeated Termux/device failures suggest an environment
problem rather than a code problem; or anything is genuinely ambiguous
about product direction rather than implementation detail.

---

## Appendix A — Open item register

Every open item from the superseded `TODO.md`, re-homed. IDs are kept
unchanged so the archived evidence stays findable. `[ ]` = open,
`[x]` = done (kept only where the note carries live information).

### Phase A1 — model foundation (§6.2)

- [ ] **7.4** — resource gate + slot-aware loader. 5/5 sub-tasks
      code-complete and code-reviewer-approved (2026-08-09). Core
      admission→load→CLI-recovery path live-verified (round 18). Left:
      a production-config live pass; re-scope against 7.4a G case (a)
      rather than re-running the old script verbatim.
- [ ] **7.4a** — swap-aware budget check. A/B/C1/C2/D/F built and
      approved; E and G run. Left: `NEW-140` scenario 3 not safely
      reproduced; `NEW-135`, `NEW-136` unfixed.
- [ ] **7.4b** — model lifecycle policy (Ish's three decisions
      confirmed 2026-08-11).
  - [ ] **A** — embed model always resident from Codey startup to
        shutdown. Implementation landed via `5687dcf`; **needs its real
        code-reviewer pass** (§4.4). Blocking prerequisite `NEW-144` was
        the kill-and-replace-a-healthy-occupant bug.
  - [ ] **B** — planner context ceiling **8192** (confirmed by Ish;
        derived from `PLANNER_PROMPT`'s ~2,446 tokens + 1,024 output
        cap = 3,470-token floor). Ready for implementer, not started.
        Adds a planner-specific constant instead of reading the shared
        `MODEL_CONFIG["n_ctx"]` global.
  - [ ] **C** — coder interactive-vs-daemon context branching
        (background ceiling **16384**, full context when a user is
        interactive). Landed + `NEW-152` fix (`6528446`); **needs
        code-reviewer + live-verifier under the real `codey-start` entry
        point**. `NEW-145`, `NEW-149`, `NEW-155` stay open.
  - [ ] **D** — revisit `MAX_CONCURRENT_MODEL_BUDGET_BYTES` (8.90GiB)
        under the new policy. Docs-only; can start immediately.
- [ ] **Lease/registry** — replace port-probe adoption with an explicit
      lease. Absorbs `NEW-104`, `NEW-144`/`NEW-146`, `NEW-149`.
      Prerequisite for a shared model server.
- [ ] **Concurrency test** — does `llama-server`'s slot/`--parallel`
      handling serve three consumers? No flag set anywhere today.

### Phase A2 — coding-domain rollout (§6.8)

- [ ] **7.3 sub-task E** — dispatch on the tier decision (A–D built,
      log-only). Must address `NEW-126` and the missing remote-tier path.
- [ ] **4.3** — wrap `core/agent.py` as a CCOS capability, unifying both
      call paths.
- [ ] **7.5** — in-flight context passing + task-context blackboard.
- [ ] **4.5** — peer-CLI escalation redesign.
- [ ] **4.6** — wire `agent_orchestrator` to real execution (Safety veto
      goes live).
- [ ] **4.7** — multi-domain request splitting.
- [ ] **9.3** — manifest schema extension (design only).
- [ ] **9.4** — limb-integration plan.
- [ ] **9.2** — generalize the gate into a multi-process
      scheduler/resource-bus.
- [ ] **external_process registration** of both limbs.
- [ ] **11.x** — Model Orchestrator. **Parked** until a domain agent
      needing it is scoped.

### Track B (§6.3–§6.7)

- [ ] **B1** — Core schema + canonical IDs.
- [ ] **B1** — the HTTP API boundary.
- [ ] **B1** — auth, roles, permissions.
- [ ] **B1** — Communication History + Audit Log (day-one-or-never).
- [ ] **B2** — create `Codey-Aigentik` fork; migrate `data/*.json` into
      the Core; write-through; point at the shared model layer.
- [ ] **B3** — CRM/Sales domain.
- [ ] **B3** — Operations domain.
- [ ] **B3** — first Automated Workflows.
- [ ] **B4** — phone-hosted public site.
- [ ] **B4** — staff/admin surface.
- [ ] **B4** — customer portal (full document/signature/financial).
- [ ] **B4** — device-limb dashboard as third API client.
- [ ] **B5a** — Finance/Bookkeeping.
- [ ] **B5a** — Marketing/Lead-Gen.
- [ ] **B5a** — Compliance monitoring/alerting.
- [ ] **B5a** — HR.
- [ ] **B5a** — Customer Service.
- [ ] **B5a** — Procurement.
- [ ] **B5a** — Global Search.
- [ ] **B5a** — Reporting/Dashboard.
- [ ] **B5b** — create `Private-Codey-Agent` fork.
- [ ] **B5b** — third-party-app automation via accessibility.
- [ ] **B5b** — Core→device scheduled-dispatch mechanism (protocol
      undesigned — §8 Q2).

### M-lane — maintenance and bugs (§6.1, unblocked, any time)

- [ ] **U.1** (`NEW-7`) — `[Recursive]`/agent planner synthesizes whole
      duplicate functions instead of targeted patches. **Narrowed**: a
      pre-registered 12-draw pass found 0/12 wrong-target (`NEW-44`
      downgraded, not closed); the remaining surface is grounding-failure
      on `main.py`-sized fixtures (3/12, same hallucinated one-line-stub
      pattern). Reinforce the existing `0026565` grounding fix against
      that pattern; do **not** add new wrong-target instructions.
- [ ] **U.2** (`NEW-50`) — worked examples in prompt text leak verbatim
      content into unrelated requests regardless of ✓/✗ labeling.
      Residual of `NEW-46`. Not scoped.
- [ ] **U.3** (`NEW-51`) — Rule 9 peer-CLI delegation format fails on a
      fresh phrasing ("Have gemini check X for race conditions") — no
      delegation step emitted. Pre-existing gap vs. regression: unsettled.
- [ ] **U.4** (`NEW-48`) — `core/plannd.py`'s `parse_steps()`
      truncation-warning heuristic false-positived 8/8, including clean
      plans. Code, not prompt. Recommend loosening or dropping it.
- [ ] **U.5** (`NEW-49`) — `core/daemon.py` hardcodes step-1 =
      Create/full-rewrite semantics by position regardless of the step's
      verb. **Refuted at n=1; still Suspected** — needs a larger sample.
- [ ] **U.6** — security hardening backlog (assign NEW-IDs when picked
      up): command-injection-via-filename in `agent.py:863-865`
      (partially addressed); daemon shell allowlist too broad in
      `task_executor.py:47-52`; Unix socket auth in `core/daemon.py`
      (peer-UID check exists; token auth recommended).
- [ ] **U.7** — H-1 fallback path is mechanism-verified only, never
      live-triggered (rule 5).
- [ ] **U.8** (`NEW-9`) — residual atfork race. **Escalation, not a fix
      task** — see §8 Q6.
- [ ] **U.9** (`NEW-69`) — interactive-CLI direct loads bypass the swap
      arbiter. **Escalation** — see §8 Q7.
- [ ] **U.10** — **open question, §8 Q8** — investigation done, decision
      pending. Attribution logging did land (commit `6859745`,
      `core/recursive.py:318-401`); the investigation Ish asked for is
      complete. Known documented gap: it covers only
      `recursive_infer()`'s two paths, never `core/agent.py`'s separate
      plain-`infer()` branch (the `step != 1` case), which produces no
      attribution line at all. Extend coverage as new work, or accept the
      gap? Ish's call.
- [ ] **U.11** (`NEW-60`, Confirmed) — a workspace-access-denied
      `read_file` sends the 7B agent into an unbounded, unrecoverable
      failure spiral (wrong-path writes, blocked shell, wandering reads,
      premature "Done."). Production-reachable independent of
      `NEW-30`/`NEW-56`. Not scoped. **High value.**
- [ ] **U.12** (`NEW-52`) — `orchestrator.py`'s own write_file-hint
      hardcoding (routed around, not fixed).
- [ ] **U.13** (`NEW-53`/`NEW-54`) — tool-completeness gaps:
      `append_file`/`note_forget` unreachable (no word→tool trigger);
      peer-CLI delegation isn't a real tool (decided by regex on raw
      text before the system prompt applies).
- [ ] **U.14** (`NEW-61`) — JSON-repair regex mangles single-quoted
      values.
- [ ] **U.15** — the 7B prompt round's Case 2 control deviation (model
      read a file anyway with content pre-injected). Reported, unresolved.
- [ ] **U.26** (`NEW-75`) — stray root-level file `=3.9.0`
      (pip-typo artifact, Suspected safe to delete; not deleted per
      rule 8).
- [ ] **U.29** (`NEW-98`, Suspected) —
      `DEVICE_CEILING_USABLE_FRACTION`/`REQUIRED_HEADROOM_FACTOR`
      calibration comment overstates the real margin (live-measured
      137MiB, not "comfortable").
- [ ] **U.30** (`NEW-99`) — `codeydOS`'s port-scoped
      `pkill -9 -f "llama-server.*8080"`/`*8081`. Rule-3 class.
      **Do with U.32.**
- [ ] **U.32** (`NEW-103`, Confirmed, live-reproduced) — `codeydOS`'s
      `stop_daemon()`/`start_plannd()` bare-pattern kills are the
      *actual* live cleanup mechanism, not theoretical. Fix: track each
      spawned server's PID at spawn and kill only that PID.
- [ ] **U.33** (`NEW-104`, Confirmed, live-reproduced) — gate slots key
      to the calling process's PID, never the spawned `llama-server`
      child's. Accounting/observability impact, not admission safety.
      Fix at both `reserve_slot()`/`mark_resident()` call sites once the
      child's PID/port are known. **Folds into the lease/registry item.**
- [ ] **U.34** (`NEW-105`, Confirmed, live-reproduced) —
      `confirm_resident_and_mark_slot()`'s `MemAvailable`-delta poll has
      never once confirmed a real load; falls through to "mark resident
      anyway" every time. Reasoned cause: `mmap`'d weight pages produce
      no clean `MemAvailable` drop. Retuning candidate: an RSS-based
      signal — needs real investigation, not a guess.

### D-lane — documentation (§6.1)

- [ ] **U.16** — `docs/architecture.md` rewrite. Best after 4.3 lands.
- [ ] **U.17** — `docs/commands.md`: 12 missing slash commands, ~13
      missing CLI flags, one possibly-stale flag (`--rollback`).
- [ ] **U.19** — TTS broken on **both** `core/voice.py` and
      `ccos/plugins/speech/tts_speech`. Get one working, verify it,
      remove the other. STT has no CCOS equivalent, so `core/voice.py`
      (or a rewrite) is needed regardless.
- [ ] **U.20** — code quality backlog: 129 F401 unused imports, 1343
      E501 line length, 74 E712 comparison style.
- [ ] **U.21** — testing gaps: no daemon-mode integration tests, no
      path-traversal tests.
- [ ] **U.22** — security guide docs: unclear whether they reflect
      recent changes; needs a read-through.
- [ ] **U.24** (`NEW-27`, Suspected) — `docs/TODO2.md` needs a scoped
      re-verification pass (2026-03-29-era list; at least one item
      already contradicted by current code).
- [ ] **U.25** (`NEW-27`) — README docs-table discoverability:
      `MODEL_COMPARISON.md`, `PRIVACY.md`, `docs/importantdoc.md` have
      real current content and no inbound link.

### Parked

- [ ] **P.1** — self-improvement activation. Gated by rule 1. See §6.9.

**Closed items retained for context:** `U.18` (telemetry dedup-key
collision, fixed 2026-08-08 — closes one *plausible* collision source,
**not** a confirmed root-cause fix for the original flakiness report;
`NEW-77`/`NEW-78` remain), `U.23` (`AUDIT_REPORT.md` archived),
`U.27`/`U.28` (`NEW-96`/`NEW-97` fixed and approved 2026-08-09),
`U.31` (`CODEY_N_CTX` override, live-verified round 18), `4.1` sub-tasks
A–E (all committed and approved; C and D live-verified).

---

## Appendix B — Findings register (NEW-1 … NEW-155)

`NEW_ISSUES.md` remains the authoritative, append-only findings ledger
and keeps its own per-issue status. **This merge deliberately did not
re-adjudicate 155 individual statuses** — doing that mechanically would
have produced confident-looking statuses this document cannot actually
stand behind, which rules 5 and 6 forbid. Read the entry in
`NEW_ISSUES.md` for any ID's real status before acting on it.

What this plan *does* carry forward is the findings that are load-bearing
for open work. Each appears in §4, §6, or Appendix A above:

**Blocking or shaping Phase A1:** `NEW-14`, `NEW-21`, `NEW-104`,
`NEW-105`, `NEW-135`, `NEW-136`, `NEW-137`, `NEW-138`, `NEW-139`,
`NEW-140`, `NEW-141`, `NEW-142`, `NEW-143`, `NEW-144`, `NEW-145`,
`NEW-146`, `NEW-149`, `NEW-151`, `NEW-152`, `NEW-153`, `NEW-154`,
`NEW-155`.

**Rule-3 (`pkill`) violations, open:** `NEW-85`, `NEW-99`, `NEW-103`.

**Gate accounting/observability, open:** `NEW-80`, `NEW-82`, `NEW-89`,
`NEW-90`, `NEW-100`, `NEW-101`, `NEW-134`.

**Agent/prompt behavior, open:** `NEW-7`, `NEW-44` (downgraded),
`NEW-48`, `NEW-49` (Suspected), `NEW-50`, `NEW-51`, `NEW-52`, `NEW-53`,
`NEW-54`, `NEW-60`, `NEW-61`, `NEW-63`, `NEW-64`.

**Device/environment, permanent conditions:** `NEW-108` (`/proc/stat`
permission-denied → CPU unmeasurable), `NEW-119` (its log-volume
consequence), `NEW-106`/`NEW-107`/`NEW-109` (observability's
`temperature`/`cpu_usage`/`memory_usage` are per-process or sampling
values, not system readings).

**Test-suite hygiene:** `NEW-110`, `NEW-150` (dirty-tree failures in
`tests/test_new19_patch_failed_repeat_escalation.py` — expected noise,
not a regression), `NEW-111` (`gui/server.py` unimportable under pytest),
`NEW-1`, `NEW-8`.

**Dead code / doc drift, low severity:** `NEW-76`, `NEW-79`, `NEW-94`,
`NEW-113`, `NEW-115`, `NEW-116`/`NEW-122`, `NEW-117`, `NEW-118`,
`NEW-120`, `NEW-121`, `NEW-123`, `NEW-124`, `NEW-125`, `NEW-127`,
`NEW-128`, `NEW-129`, `NEW-130`, `NEW-132`, `NEW-147`, `NEW-148`.

---

## Appendix C — The CRM module breakdown (Ish's own words, verbatim)

Carried forward unchanged from the archived `Codey-Restoricon-OS.md`
Appendix A (itself verbatim from Ish, 2026-08-21). This is the
field-level source spec for §3.3's Core. **Edit field lists here, once —
not in two places.**

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
    (Folded into §3.1 as the architecture principle, not a separate
    build item.)
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

---

## Appendix D — Repo structure

Directory-level, deliberately not a per-file inventory (that level of
detail goes stale fast and has produced repeat findings, `NEW-26`/
`NEW-27`, when it did). For exact file lists, list the directory.

```
Codey-OS/
├── .github/            GitHub workflows + repo description
├── assets/             Static assets (mascot image, demo GIF)
├── ccos/               Cognitive OS layer (the OS shell)
│   ├── core/           capability_registry, plugin_manager,
│   │                   agent_orchestrator, device_manager, sandbox,
│   │                   tool_router, telemetry_engine, performance_tracker,
│   │                   lifecycle_manager, planner, reflection_engine,
│   │                   memory/, plus the gated self-improvement modules
│   ├── data/           Persistent CCOS state
│   ├── demo_*.py       Demo scripts per subsystem
│   ├── plugins/        compound/, research/, speech/, system/, vision/
│   └── tests/          CCOS test suite
├── core/               Coding agent: agent.py, daemon.py, loader_v2.py,
│                       memory_v2.py, orchestrator.py, plannd.py,
│                       planner*.py, recursive.py, symbolic_graph.py,
│                       inference*.py, resource_gate.py, model_tiers.py,
│                       embed_server.py, checkpoint.py, thermal.py,
│                       sysmon.py, observability.py, recovery.py,
│                       githelper.py, peer_cli.py/peer_shell.py,
│                       voice.py (TTS/STT, broken)
├── docs/               Documentation + docs/archive/ (superseded docs,
│                       see below)
├── gui/                index.html + server.py (WebSocket server)
├── lib/                Shared shell helpers (gui_launch.sh)
├── pipeline/           Training-data pipeline
├── prompts/            system_prompt.py, layered_prompt.py,
│                       critique_prompts.py
├── tests/              Codey-OS test suite, incl. tests/security/
├── tools/              file_tools, patch_tools, shell_tools, kb_scraper,
│                       kb_semantic, setup_skills.sh
├── utils/              config.py, file_utils.py, logger.py
├── codey-start / codey-stop   Unified entry points
├── codeyOS / codeydOS         CLI / daemon launcher scripts
├── install.sh                 Must stay current (rule 11)
├── main.py                    CLI entry point
├── CODEY_MASTER_PLAN.md       ← THIS FILE, authoritative, start here
├── AGENTS.md                  Start-here pointer for non-Claude agents
├── CLAUDE.md                  Ground rules in Claude Code's format
├── NEW_ISSUES.md              Findings ledger (rule 8)
├── PROJECT_LOG.md             Round-by-round record (rules 7, 9)
├── LIVE_TEST_QUEUE.md         Live tests deferred for Ish himself
├── PENDING_ISH_DECISIONS.md   Fully resolved; kept as the record of four
│                              capability-wrapping decisions (see §9)
└── README.md / CHANGELOG.md / PRIVACY.md / MODEL_COMPARISON.md /
    Codey-OS-audit.md
```

`docs/archive/` holds `CODEY_OS_MASTER_VISION.md`, `TODO.md`,
`WORK_QUEUE.md`, `PROJECT_PLAN.md`, `Codey-Restoricon-OS.md`, and
`AUDIT_REPORT.md` — evidence only.
