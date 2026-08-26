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

### 1.4 One model for everything (Ish, 2026-08-22) — supersedes the two-model split

**Decision, given directly in-session: the Qwen2.5-Coder-7B primary and
the Qwen2.5-Coder-1.5B planner are both retired. `Qwen3.5-4B-Q4_K_M`
becomes the single default model for every role, and it does its own
planning by running in thinking mode instead of handing off to a separate
planner model.**

This is a settled decision, not a proposal. What it changes runs through
almost every platform item in §6.2, so the consequences are stated here
once and referenced from there.

**The model, verified from the file on disk** (GGUF header read directly,
no model loaded — `~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf`,
2,740,937,888 bytes / 2.553GiB):

| GGUF field | Value |
|---|---|
| `general.architecture` | `qwen35` |
| `qwen35.block_count` | 32 layers |
| `qwen35.attention.head_count` / `head_count_kv` | 16 / **4** (GQA) |
| `qwen35.attention.key_length` / `value_length` | **256** / 256 |
| `qwen35.embedding_length` | 2560 |
| `qwen35.context_length` | **262144** (256K native) |
| `qwen35.full_attention_interval` | **4** → 32/4 = **8 full-attention layers** |
| `qwen35.ssm.state_size` / `ssm.inner_size` | **128** / **4096** |
| `qwen35.ssm.conv_kernel` / `ssm.group_count` / `ssm.time_step_rank` | 4 / 16 / 32 |

**This is a hybrid Transformer-SSM model, not a conventional attention
model.** Of its 32 layers, **8 are full-attention** (16 Q heads / 4 KV
heads, head dim 256) and **24 are SSM/linear-attention** layers carrying
a fixed-size recurrent state that **does not grow with context**. Only
the 8 full-attention layers contribute a growing KV cache. The `ssm.*`
metadata block above is what establishes this, and it is why §5.1's cost
arithmetic looks nothing like the retired models'.

**Thinking mode is a per-request switch, default off — verified from the
model's own chat template** (7,816 chars, read from the GGUF): the
template branches on `enable_thinking`. When it is defined and true it
emits `<think>\n` and the model reasons; otherwise it emits an empty
`<think>\n\n</think>` block, forcing non-thinking mode. Prior turns'
reasoning is parsed back out via `reasoning_content`. So:

- The coding path is **unaffected unless we opt in** — no flag, no
  thinking, no behavior change to what the agent does today.
- The planning path opts in **per request**. No second model, no second
  server, no second port, no swap between them. That is precisely the
  substitution Ish is asking for.

**The local toolchain already supports all of this** — verified by
inspecting the installed `llama-server` binary (2026-08-11 build,
`~/llama.cpp/build/bin/llama-server`), which carries the `qwen35`
architecture plus `--jinja`, `--reasoning-format`, `chat_template_kwargs`,
`enable_thinking`, and `reasoning_content`. **But `--jinja` is not
currently passed** by `core/loader_v2.py`'s spawn command (`_spawn_locked`,
~line 331), which means the GGUF chat template — and therefore
`enable_thinking` — is inert as the system stands today. That is a
concrete prerequisite, not a detail (`NEW-158`).

**Why this helps as much as Ish expects it to.** The single hardest
open problem in §4.3 was concurrent primary + planner residency at
production context — `NEW-141`, reproduced live, unsolved. With one
model there is no concurrent pair to arbitrate. The problem does not get
mitigated; it structurally stops existing. Several derived constants and
a whole sub-task of policy go with it (§5, §6.2).

**It is also dramatically cheaper on context than the model it replaces**
— 32,768 bytes per token of KV against the 7B's 57,344, i.e. **0.571x**,
because only 8 of its 32 layers keep a growing cache. At the current
production `n_ctx=32768` it costs ~3.83GiB against the 7B's 6.36GiB, and
it can carry **65536 — double the current context — for less than the 7B
needed for half of it** (§5.1). Its native ceiling is 262144; what limits
us is the device budget, not the model.

**Correction on the record, per rule 6.** The first version of this
section (same day) asserted the opposite — that the 256-wide head dim
made its KV cache 2.29x the 7B's — by applying a conventional
all-layers-attend formula to a model that does not work that way, and by
reasoning from the older Qwen3-4B's behavior on the strength of a similar
name. Ish corrected it. The error is preserved here rather than quietly
overwritten because it is the exact failure **rule 14** now exists to
prevent, and because the corrected numbers change a real decision (§8 Q1
flips from "how far must the context come down" to "how far can it go
up").

**What still needs measuring, and is genuinely open:** the gate's
`ModelArch` could not express hybrid attention at all — **M1-A fixed that
2026-08-22 (code-complete, review pending): `n_attention_layers=8` now
drives the KV term (`NEW-157`)**. The 24 SSM layers' constant state is
still estimated, not measured, and is now carried explicitly as
`recurrent_state_bytes` (§5.1). M1-E is where both get real numbers.

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
   concurrent model loads. Before any live test that loads any local
   model (the Qwen3.5-4B default, the embedding model, or a retired
   7B/1.5B during migration): run `free -h` and record it verbatim. Never
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


14. **Never assume — read the artifact. And when you read it, read all of
    it.** No factual claim about an external artifact — a model, a
    library, an API, a binary, a config file — may be stated from prior
    knowledge, from documentation about a *similar* thing, or from family
    resemblance to something with a related name. Go to the artifact and
    check. This rule exists because of a real, dated failure: on
    2026-08-22 this plan asserted that Qwen3.5-4B's KV cache was 2.29x
    the retired 7B's, by applying a conventional 32-layer-attention
    formula to a model that is nothing of the kind. It is a hybrid: 8
    full-attention layers and 24 SSM/linear layers whose state does not
    grow with context. The real figure is **0.571x** — the opposite
    direction, and a ~2.5GiB difference in what this device can carry.
    Ish caught it; the docs did not.

    Two specific traps that failure exposed, both binding:
    - **Model-family names are not evidence.** Qwen3.5 is not Qwen3 with
      a bigger number. A shared prefix says nothing about layer counts,
      attention mechanism, KV layout, or context handling. The same goes
      for library and API versions.
    - **Do not grep for the keys you expect.** The first inspection of
      that GGUF filtered metadata against a list of anticipated field
      names, and therefore never saw the `ssm.*` block that defined the
      architecture. **Dump the full key set first, then narrow.** A
      filtered read that confirms your expectation is the most dangerous
      kind of evidence, because it looks like verification.

    Reading a file, parsing a header, or inspecting a binary's strings is
    cheap and safe (none of it loads or executes a model — see rule 2 for
    what actually requires care). There is no excuse for guessing.

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

**As of §1.4 this is one model, not a fleet**: Qwen3.5-4B serves every
role — coding, planning (via thinking mode), conversation, and whatever
domain work comes later — alongside the separate, small, always-resident
embedding model. One shared local model server, used by Codey-OS and both
limbs, with Codey-OS tracking access so nothing gets crossed. Three
distinct problems remain inside that, and the decision shrinks two of
them:

- **Concurrent requests** — now the *primary* problem rather than one of
  several, because a single server has to serve the daemon, the TUI/GUI,
  and eventually both limbs. Likely solvable via `llama-server`'s
  slot/`--parallel` handling; **unverified — no such flag is set anywhere
  Codey-OS launches `llama-server` today.** Test this directly before
  building anything more elaborate.
- **Model residency** — **largely dissolved.** With one generation model
  plus the embedding model, there is no primary-vs-planner pair to
  arbitrate, no sequential swap, and no concurrent-pair admission case
  (`NEW-141`). The gate still owns admission for the one model, and the
  budget arithmetic still has to be re-derived (§5) — but the hard part
  of the problem is gone, not deferred.
- **Adoption vs. leasing** — unchanged and still real. `core/loader_v2.py`
  decides "is my server already running?" by probing port 8080. A shared
  model server needs an explicit lease/registry, not a port-occupancy
  guess that `core/embed_server.py`'s `_kill_port_occupant()` can act on.
  Tracked as the lease/registry item in §6.2 (and by
  `NEW-104`/`NEW-144`/`NEW-149`). **One model shared by more consumers
  makes this more important, not less.**

**Thinking mode replaces the planner role, not the planner's design
questions.** The 1.5B model goes away; what does not go away is deciding
*when* to think (every planning call? only above a complexity threshold?
— the classifier in 7.3 is the natural place for that judgment), how the
`<think>` block is stripped before `core/plannd.py:parse_steps()` sees
it, and what the thinking budget costs in wall-clock on this device.
§6.2's M1 owns those; §8 Q8 is the policy question inside it.

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

## 4. Where things actually stand (2026-08-22)

This section is the current-state snapshot. Keep it accurate; it is the
first thing a new session reads after the rules.

**Read §4.1 and §4.2 with one qualifier in mind:** every live-verified
result below was measured against the **retired** Qwen2.5-Coder-7B and
1.5B models (§1.4). The *mechanisms* they verify — gate admission, slot
reservation, CLI recovery, dispatch gating, the shutdown tripwire — are
model-independent and remain verified. The *numbers* are not transferable
to Qwen3.5-4B; §5.1 has the new arithmetic and M1-E is where it gets
measured. Nothing below is being retroactively downgraded; it is being
scoped to what it actually proved.

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

- **M1-A (arch + cost correctness in `core/resource_gate.py`)** —
  code-complete **and code-reviewer-reviewed** 2026-08-22, landed as
  `a030bbf`. The pass returned one blocking finding (C-1,
  `recurrent_state_bytes` derived by analogy with Mamba instead of from
  llama.cpp's allocator — 25,755,648 corrected to 52,690,944); it was
  fixed, re-verified, and the reviewer's own re-review corrections (the
  drained-assertion line refs, the four→five `ModelArch(` call-site
  count) are incorporated in the committed state. Unit-tested only, by
  design: 200 passed across `tests/test_resource_gate.py` +
  `tests/test_new84_stale_model_path.py`, 739 passed / 1 skipped
  repo-wide post-fix (the excluded file is
  `tests/test_new19_patch_failed_repeat_escalation.py`, the known
  dirty-tree noise, `NEW-110`/`NEW-150`). No model was loaded; **there is
  no live component to this sub-task**, so "live-verified" is not a
  status it can reach. See Appendix A for what changed.

  **Record gap CLOSED, 2026-08-23.** The confirmatory sign-off promised
  above landed as part of the M1-B/C/D review pass: `code-reviewer`
  independently re-derived `recurrent_state_bytes = 52,690,944` from the
  real llama.cpp source at the pinned commit (`91d2fc38`) and confirmed it
  matches `a030bbf`'s committed value exactly. No discrepancy — nothing to
  downgrade per rule 6.

- **M1-B / M1-C / M1-D (config repoint, spawn flags, planner-server
  collapse) — code-complete, code-reviewer-approved 2026-08-23 across two
  review passes, landed as `841ef2e`.** No live
  component to any of the three by design — no model has been loaded this
  round, everything is code + unit-test. `git status` at the time of this
  entry shows the full diff staged in the working tree, not on a commit;
  the checkbox language in Appendix A is written to remain accurate
  whether read before or after that commit lands.
  - **M1-B** (`utils/config.py`): `MODEL_PATH`/`PLANNER_MODEL_PATH`
    repointed to `~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf`;
    `SECONDARY_MODEL_PATH` removed as confirmed-dead code (`core/model_
    tiers.py` had already established mutating it alone had no effect on
    what actually loaded); `QWEN_7B_MMAP`/`QWEN_7B_MLOCK` renamed to
    `QWEN_MMAP`/`QWEN_MLOCK`; `n_ctx` default 32768 → 65536 (§8 Q1).
    Closes `NEW-161` (the interim 768MiB unsafe-direction KV
    under-estimate — closed the instant `MODEL_PATH` moved off the 7B).
  - **M1-C** (`core/loader_v2.py:_spawn_locked()`): added `--jinja` and
    `--reasoning-format deepseek` to the spawn command. Code-reviewer
    independently resolved `NEW-162`'s open question by dumping the
    actual GGUF chat template (the artifact itself, not `--help` text or
    family resemblance — rule 12 discipline): thinking mode is **off by
    default** — a caller that doesn't opt in gets an already-closed empty
    `<think></think>` block, so the coder/summarizer paths were never at
    risk from the new flags. `NEW-162` itself **stays open/Suspected** — a
    live spawn is still the final word — tracked into M1-E.
  - **M1-D**: planner server collapsed onto the primary server.
    `core/planner_loader.py` deleted (322 lines).
    `_evict_planner_and_confirm_free()` in `core/loader_v2.py` deleted —
    closes `NEW-142`. All three `codeydOS` port-8081
    `pkill -9 -f "llama-server.*8081"` sites confirmed gone (verified
    independently by this session and by code-reviewer) — closes the
    8081 half of `NEW-99`/`NEW-103`; the 8080-pattern `pkill` sites remain
    in `codeydOS` and stay open under the same finding numbers. `NEW-100`
    and `NEW-101` close (the planner gate-slot registration they describe
    no longer exists). `NEW-124` closes (the stale "0.5B" comment in
    `core/planner_service.py` is fixed). `NEW-137`, `NEW-140` scenario 3,
    `NEW-141`, `NEW-143`: the code-read half is satisfied (the retired
    paths are confirmed gone, not merely unused) but per `NEW-159`'s own
    disposition note these need M1-E's live numbers too before fully
    closing — recorded here as **code-read confirmed, pending M1-E**, not
    closed.
  - **Fix round** (code-reviewer's one required change, first pass):
    `core/lora_import.py`'s `swap_to_finetuned_model()` "primary" branch
    now mutates and rolls back both `cfg.MODEL_PATH` and
    `cfg.PLANNER_MODEL_PATH` together — it was asymmetric with the
    "secondary" branch, and the asymmetry could have merged a LoRA onto
    the wrong base file. New test `tests/test_lora_import_swap_sync.py`.
    This surfaced a new, separate, pre-existing bug, logged and left open
    as `NEW-163`: `rollback_to_backup()` copies backup weights onto
    whatever `cfg.MODEL_PATH` currently names, which after a swap is the
    fine-tuned file's path — a rollback could write base weights into the
    fine-tuned file's name. Out of scope to fix in this round.
  - **install.sh** (rule 11 compliance, fixed in the same round per the
    rule's requirement): retired 7B/1.5B downloads removed; now downloads
    Qwen3.5-4B from
    `https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf`
    — verified live via `curl -I` by both implementer and code-reviewer
    independently, a 302 redirect with a matching filename and
    `x-linked-size: 2740937888`; stale "1.5B planner (port 8081)"
    post-install text corrected.
  - **Two code-reviewer passes total.** First pass: M1-B APPROVED, M1-C
    APPROVED, M1-D CHANGES REQUESTED (the `lora_import.py` fix above) plus
    the `install.sh` rule-11 gap. Second/final pass: APPROVED all three
    phases as one combined, ready-to-commit state. Both of §4.4's
    previously-unreviewed folded-in diffs (7.4b sub-task A, the `NEW-152`
    fix) were explicitly reviewed in the first pass and returned
    APPROVED — this closes §4.4's outstanding process debt.
  - **Test suite, final state, verbatim** (reproduced independently three
    times this round — implementer, project-architect, and
    code-reviewer, all matching): `tests/` → **647 passed, 1 skipped**;
    `ccos/tests/` → **68 passed**. Combined **715 passed, 1 skipped**.
    Baseline before this round was 743 passed / 1 skipped on the *old*
    two-server architecture; net movement includes ~30 tests deleted
    because their subject module/constant was deleted by the planner
    collapse (verified by code-reviewer as genuine deletions of
    now-nonexistent functionality, not concealed failures), plus a few
    new tests added for the M1-C spawn flags and the M1-D `lora_import.py`
    fix.
  - **What this round does NOT reach, stated plainly:** M1-E (live
    verification — no model has been loaded this round, everything is
    code + unit-test only), M1-F (constants re-derivation, waits on
    M1-E), and M1-G (prompt re-check, waits on M1-E). "Live-verified" is
    not a status this round can reach, the same framing §4.2 already
    applies to M1-A.

- **M1-E (live verification) — DONE 2026-08-23, fully live-verified on
  real device via `main.py --no-resume`** (chosen deliberately over the
  full `codey-start` because the daemon+GUI would have consumed headroom
  this device didn't have to spare that session — but it routes through
  the identical `core/loader_v2.py:_spawn_locked()` code path, so the
  migration's own spawn logic was genuinely exercised, not bypassed).
  Three load/unload cycles, each PID individually tracked and killed
  (never `pkill -f` by pattern), confirmed fully unloaded between and
  after (`ps aux | grep llama-server` clean). `free -h` baseline: 5.3Gi
  available before, 6.7Gi available after, all three cycles complete.
  - **`NEW-157` CLOSED with measurement.** Real RSS across three
    independent spawns clustered 2-10% above M1-A's point estimate of
    5,209,547,936 bytes (4.8518GiB at `n_ctx=65536`): 5.19GiB, 5.1645GiB,
    5.3431GiB, 4.9476GiB — all comfortably inside the ×1.25 headroom
    factor (6.065GiB required vs. ~4.95-5.34GiB actual peak). The hybrid
    fix (8 attention layers, not the old all-32-attend formula) is
    confirmed directionally and quantitatively correct — nowhere near the
    ~4x error the pre-fix formula would have produced.
  - **`NEW-158` CLOSED.** `--reasoning-format deepseek` genuinely splits
    `message.content` from `message.reasoning_content` in real server
    responses, confirmed via a real thinking-mode request — not a no-op.
    `parse_steps()` correctly reads `.content` only.
  - **`NEW-160` CLOSED (upgraded from Suspected).** The real 7,816-char
    `tokenizer.chat_template` was extracted from the live GGUF and
    rendered with real jinja2 against a plain-text message with both
    `enable_thinking=False` and `True` — no vision-namespace tokens
    leaked into rendered output for either case. A real coding-path
    inference request in the same session independently confirmed clean
    output with no role-framing corruption. The vision branches are
    confirmed inert for text-only requests.
  - **`NEW-162` CLOSED with a caveat.** A true A/B (flags present vs.
    absent) wasn't feasible without a code change, since
    `--jinja`/`--reasoning-format` are hardcoded in `_spawn_locked()`,
    not env-toggleable, so the strict "off vs. on" comparison from the
    original bug report's framing was never run. Response-shape evidence
    with flags present shows the mechanism working correctly
    (`reasoning_content` genuinely separate from `content` under
    `enable_thinking: true`) — enough to say the flags demonstrably do
    something, which is the question this finding actually turned on.
  - **Flash-attention activity — LEFT OPEN, not confirmed either way.**
    No positive confirmation was found that `--flash-attn on` is actually
    active vs. silently falling back — the specific llama.cpp log line
    that would confirm it never appeared at this build's default log
    verbosity. Needs a higher-verbosity spawn or a different check; not
    glossed over as "probably fine."
  - **Two new findings from this live session — `NEW-164` and `NEW-165`
    (see `NEW_ISSUES.md`), both open at the time this entry was written,
    since CLOSED — see the M1-E-fix entry below and `PROJECT_LOG.md`'s
    2026-08-23 M1-E-fix entry.** `NEW-164`: `PLANNER_MAX_TOKENS=1024` is
    confirmed, live, too small —
    a real thinking-mode planning request spent its entire budget on the
    reasoning trace and returned `content: ""`, so `get_plan()` silently
    returned `None`. Planning silently degrades to unplanned execution.
    This is a real, currently-live production defect, not a theoretical
    risk. `NEW-165`: `get_plan()`'s hardcoded `timeout=60` is shorter
    than this device's real prompt-processing time for the planner's
    prompt (~2,425 tokens takes over 60s to prefill alone at ~23-26 t/s)
    — a request can be cancelled server-side before generation even
    starts, an independent failure mode that fires *before* `NEW-164`'s
    scenario even gets a chance to manifest. **Recommendation (acted on
    same round as M1-E-fix): bundle NEW-164+NEW-165 into one fix task
    (found together, same function, same live session) and run it BEFORE
    M1-F/M1-G** — planning is
    currently broken on real prompts, a more urgent problem than either
    of those two follow-on sub-tasks. The fix task that followed also
    surfaced and closed two further layers, `NEW-167` and `NEW-169` (see
    Appendix A's M1-E-fix entry) — this M1-E entry is left as originally
    written to record M1-E's own findings honestly, not edited to read as
    if the fix had already happened.
  - **Real latency data captured (§8 Q8's cost question, reference
    data):** non-thinking coding requests: 177.9s for 124 tokens
    (7.0 t/s), 135.7s for 578 tokens (5.7 t/s). Thinking-mode planning
    request: 315.16s total (104.86s prompt processing at 23.13 t/s +
    210.2s generation at 4.87 t/s) for 1024 tokens that never reached an
    answer. Thinking mode is markedly slower per generated token and, per
    `NEW-164`, can burn its whole budget with nothing to show for it.
  - **What M1-E does NOT settle:** `NEW-137`, `NEW-140` scenario 3,
    `NEW-141`, `NEW-143` (§4.3) still need their own re-check against
    these live numbers before closing — this entry records M1-E's own
    findings, not a blanket close of every item that was "pending M1-E."
    M1-F (constants re-derivation) and M1-G (prompt re-check) have not
    run. The round as a whole is not "M1 fully live-verified" until the
    `NEW-164`/`NEW-165` fix and M1-F/M1-G also land.

### 4.3 The one honest platform gap — largely dissolved by §1.4

**As it stood on 2026-08-21:** concurrent primary + planner at
`n_ctx=32768` did not work on this device. 7.4a sub-task G case (b)
reproduced `NEW-14`'s swap-distress shape live with the 10GiB swap-assist
cap in place (`NEW-141`); the `NEW-140` low-swap-headroom single-model
scenario was deferred, not safely reproduced.

**As of §1.4 (2026-08-22) there is no model pair.** `NEW-141` and
`NEW-140`'s scenario 3 describe a configuration that no longer exists —
they close on the decision rather than on a fix. **Confirmed against the
code by M1-D, 2026-08-23:** the retired paths (`core/planner_loader.py`,
`_evict_planner_and_confirm_free()`) are actually gone, not merely
unused — but per `NEW-159`'s own disposition note these still need M1-E's
live numbers before fully closing, so they remain **code-read confirmed,
pending M1-E**, not closed outright.

**`NEW-142` is the exception that was never meant to be closed by
decision — and it CLOSED on a code read, 2026-08-23, exactly as this
paragraph specified.** It was `planner_loader.ensure_planner()` evicting
the primary *by bypassing the gate's reserve path* — the eviction-bypass
is what made `NEW-141` reproducible in the first place. M1-D deleted
`core/planner_loader.py` in full (322 lines) and deleted
`core/loader_v2.py:_evict_planner_and_confirm_free()`, the obvious
survivor this paragraph named to check — confirmed gone by direct code
read, not inferred from the model-migration decision.

**What did not dissolve, and what replaced it:** the gate's cost model is
pointed at the wrong architecture until M1-A fixes it, and the budget
constants derived from the retired pair are stale (§5.1, `NEW-156`). The
open question is no longer "can two models coexist" but "the gate
over-estimates this model's KV by ~4× until it learns the hybrid split"
(`NEW-157`) — a bounded, safe-direction error with a known fix, which is
a considerably better problem to have. On the numbers in §5.1 the device
now has headroom it did not have a week ago, including room to *raise*
the context ceiling (§8 Q1, answered 2026-08-22: 65536).

Still open and unaffected by §1.4: `NEW-138` (an unexplained ~1.56GiB
anon-RSS gap — worth re-checking against the new model, since the figure
was measured on the 7B), `NEW-139` (`--mmap` makes quantized-weight zram
compression structurally unmeasurable). **Correction, rule 6 (2026-08-23):
`NEW-137` and `NEW-143` are NOT yet closed** — both are specifically about
the 7B at 32768 and their retired code paths are now confirmed gone by
M1-D's code read, but per `NEW-159`'s disposition note they still need
M1-E's live numbers before closing outright. This line previously said
"closed by retirement"; that overstated it.

### 4.4 Outstanding process debt — review-pass debt CLOSED 2026-08-23, live-verify still pending M1-E

**Review-pass half CLOSED.** The M1-B/C/D `code-reviewer` brief explicitly
included the two previously-unreviewed rule-4 diffs described below (7.4b
sub-task A, the `NEW-152` fix) as in-scope, per point 1 below, and the
first of the two review passes returned APPROVED on both. The "no
mandatory review happened" gap this section originally recorded is
closed. **What is NOT closed:** point 2 below — `live-verifier` covering
both under the real `codey-start` entry point — which still waits on
M1-E, same as the rest of this round.

**Rule 4 has live debt.** `NEW-151` recorded a self-found process
violation: commit `5687dcf` swept in two already-implemented,
rule-4-category process-lifecycle changes (7.4b sub-tasks A and C)
without the mandatory `code-reviewer` pass. A retroactive review found a
Critical gap (`NEW-152`, sticky `_ever_loaded` reopening `NEW-145` after
adoption), which was then fixed in commit `6528446` — but **that fix is
itself code-complete only, not code-reviewer-approved and not
live-verified.** `NEW-145`, `NEW-149`, and `NEW-155` stay open.

**Sequencing changed 2026-08-22.** This debt used to be listed as "clear
it before any new 7.4b work." Under Ish's direction to migrate the model
first (§6.2), it is instead **folded into M1's own mandatory review
pass** — because M1 touches the same files (`core/loader_v2.py`,
`core/daemon.py`, `core/embed_server.py`, `core/inference.py`), and
reviewing a superseded intermediate state before changing it again is
wasted effort. **The gate is not being relaxed, only re-pointed:**

1. When M1's diffs go to `code-reviewer`, the brief must say explicitly
   that two previously-unreviewed rule-4 diffs are in scope as part of
   the combined state: 7.4b sub-task A (`EmbedServer.is_healthy()`,
   `core/inference.py:_start_server()`) and the `NEW-152` fix
   (`_ever_spawned`/`was_ever_spawned()` in `core/loader_v2.py`,
   `_watchdog_check_model()` in `core/daemon.py`). A reviewer who only
   sees M1's own delta will miss them.
2. `live-verifier` covers both as part of M1-E, **under the real
   `codey-start` entry point** — `NEW-145` was only ever found under the
   real entry point, never under a synthetic harness. That constraint is
   unchanged and non-negotiable.
3. If M1 slips or is abandoned, this debt reverts to standalone and must
   be cleared on its own. It does not expire by being folded in.

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
- `MAX_SWAP_ASSIST_BYTES` = **6.50GiB** (re-derived by M1-F, 2026-08-24,
  from the retired 10.00GiB — see below); `REQUIRED_HEADROOM_FACTOR` =
  1.25; `DEVICE_CEILING_USABLE_FRACTION` = 0.60 (→ device ceiling
  ~6.49-6.50GiB live, drifts slightly with MemTotal reads).
  `MAX_CONCURRENT_MODEL_BUDGET_BYTES` = **7.00GiB** (re-derived by M1-F
  from the retired 8.90GiB — see below).

### 5.1 Model costs under the one-model decision (§1.4)

**Qwen3.5-4B is a hybrid: 8 full-attention layers + 24 SSM/linear
layers** (§1.4, established from the GGUF's `full_attention_interval = 4`
over `block_count = 32`, plus the `ssm.*` block). Only the 8
full-attention layers grow a KV cache with context; the 24 SSM layers
hold a fixed-size recurrent state. So the KV term uses **8**, not 32:

`2 bytes (fp16) × 2 (K+V) × 8 layers × 4 kv_heads × 256 head_dim`
= **32,768 bytes per token.**

| Model | Layers contributing KV | Bytes per token |
|---|---|---|
| **Qwen3.5-4B** (new default) | **8** of 32 (hybrid) | **32,768** |
| Qwen2.5-Coder-7B (retired) | 28 of 28 | 57,344 |
| Qwen2.5-Coder-1.5B (retired) | 28 of 28 | 28,672 |

**The new model costs 0.571× the retired 7B per token of context** — a
~43% reduction, not the increase an all-layers-attend formula would
predict (see §1.4's correction and rule 14).

Totals = file (2.553GiB) + KV + the 0.250GiB compute-overhead constant +
50.25MiB of SSM state (context-independent, see note 2):

| `n_ctx` | KV | Total | Required (×1.25) | vs ~6.49GiB ceiling |
|---|---|---|---|---|
| 32768 (current default) | 1.000GiB | **3.852GiB** | 4.815GiB | comfortable |
| 65536 | 2.000GiB | 4.852GiB | 6.065GiB | **admissible — 2× the context** |
| 131072 | 4.000GiB | 6.852GiB | 8.565GiB | hard-reject |
| 262144 (model's native max) | 8.000GiB | 10.852GiB | — | hard-reject |

**For comparison:** the 7B alone cost 6.361GiB at 32768 and sat ~137MiB
from the hard-reject ceiling (`NEW-143`). The retired pair cost 8.527GiB
declared concurrently — the case `NEW-141` proved this device cannot
sustain. The new model at the *same* context costs 3.852GiB, and can run
at **double** it for 4.852GiB. The one-model decision buys both a
simpler residency problem and materially more context than before.

**Three figures above are computed, not measured:**

1. **The gate now knows the hybrid split — M1-A, 2026-08-22,
   code-complete (not yet code-reviewer-approved).** `ModelArch` gained
   `n_attention_layers` (8) and `recurrent_state_bytes`, and
   `KNOWN_MODEL_ARCHS` points both roles at the new `QWEN35_4B_ARCH`
   (`NEW-157`). A unit test now pins the exact total in this table's
   32768 row — 4,135,806,112 bytes = 3.852GiB — so a future edit that
   "corrects" the 8 back to 32 fails loudly. Before that fix the gate
   computed the KV term from 32 layers and over-estimated by ~4×; that
   was the safe direction, but it would have wrongly capped `n_ctx` at
   32768 when 65536 is affordable.
2. **The SSM state figure is 50.25MiB, derived from llama.cpp's
   allocation code — still not measured.** **Correction, rule 6
   (2026-08-22, caught in M1-A's review):** this document previously
   published ~25MiB, derived as `inner_size × (conv_kernel − 1) +
   inner_size × state_size` per layer, **fp16**, × 24 layers, and warned
   that "llama.cpp's actual allocation may differ in layout or element
   width." It differed in *exactly both* ways, and the allocating source
   was on this device the whole time (`~/llama.cpp`, commit `91d2fc38`):
   - `llama-hparams.cpp:204` — the conv term is `(ssm_d_conv − 1) ×
     (ssm_d_inner + 2 × ssm_n_group × ssm_d_state)`. The old formula
     **omitted `ssm.group_count = 16`**, halving that term.
   - `llama-model.cpp:2153-2155` — qwen35 passes `recurrent_type_k` and
     `recurrent_type_v` as **`GGML_TYPE_F32`**. Four bytes, not two. The
     "fp16" above was asserted as fact and was wrong; recurrent state
     does *not* follow the KV cache's element width.

   Corrected: `((4−1) × (4096 + 2×16×128) + 128×4096) × 4 × 24` =
   **52,690,944 bytes (50.25MiB)**, an under-estimate of 26,935,296
   bytes in the old figure. It remains small and context-independent, so
   the table's shape is unchanged and **§8 Q1's answer of 65536 still
   holds** (6.065GiB required against the ~6.49GiB ceiling). Reading the
   allocator is stronger evidence than the formula it replaced, but it is
   still **source-derived, not measured** — M1-E keeps that task. One
   property the old note missed entirely: llama.cpp allocates recurrent
   state **per sequence slot** (`llama-memory-recurrent.cpp:100-101`),
   so 50.25MiB is one slot's worth and scales with `--parallel`.
3. **Everything here is arithmetic and source-reading, not
   measurement.** M1-E measures real resident cost and settles all of it.

**Constants below — CLOSED by M1-F, 2026-08-24** (`NEW-156`):

- ~~`MAX_CONCURRENT_MODEL_BUDGET_BYTES` = 8.90GiB was derived precisely as
  7B + 1.5B + embed at 32768. Two of those three models no longer exist
  in the system.~~ **Re-derived to 7.00GiB.** Computed via
  `estimate_model_load_cost()` against the real on-disk primary/embed
  files: interactive primary (n_ctx=65536) + embed raw sum =
  5,562,090,016 bytes (~5.1801GiB). M1-F's first-pass value from that sum
  alone (5.25GiB) was too low — it sat BELOW `compute_device_ceiling_bytes()`
  (~6.4949GiB live), which the project's own existing single-model tests
  immediately caught (a single model near the device ceiling was wrongly
  refused via `budget_ceiling_exceeded`), surfacing a previously
  undocumented, untested ordering requirement between the two constants
  (`NEW-179`). Final value, 7.00GiB, clears both the device ceiling
  (~0.505GiB margin) and the concurrent raw sum (~1.4GiB margin). Full
  derivation and the invariant fix in `core/resource_gate.py`'s own
  comment; regression test `test_max_concurrent_budget_at_least_device_ceiling`
  in `tests/test_resource_gate.py` now pins the ordering directly.
- ~~`MAX_SWAP_ASSIST_BYTES` = 10.00GiB was calibrated (7.4a sub-task F)
  specifically to make the 7B at 32768 reachable through swap assist.
  That target no longer exists.~~ **Re-derived to 6.50GiB.** Live formula
  (`compute_swap_assisted_headroom_bytes()`, fresh `/proc/meminfo` reads,
  not the 2026-08-11 session's) gave `gated_swap_free` ~7.14-7.23GiB
  (two reads seconds apart, confirming real sample-to-sample drift). New
  value sits ~0.435GiB above the interactive worst case's required cost
  (~6.065GiB, ×1.25 headroom) and ~0.6-0.7GiB below the live ceiling —
  a real, binding margin, not a number set high enough to never bind.
  **Stated explicitly, per rules 6/7:** this does NOT restore the
  plain-`MemAvailable` check to binding for the interactive worst case —
  that property (§4.3's original observation) is unchanged in direction,
  only reduced in magnitude from 10.00GiB. Full derivation in
  `core/resource_gate.py`'s own comment.
- Embed model's real resident RSS remains unmeasured (`NEW-180`, spun off
  this round) — both constants above still use the same file-size-only
  floor estimate (352,542,080 bytes, ~0.328GiB) every derivation back to
  7.4a has used. Not currently load-bearing at 7.00GiB/6.50GiB's margins,
  but the number itself has never been checked against reality.
- ~~`core/resource_gate.py`'s `KNOWN_MODEL_ARCHS` maps `"primary"` →
  `QWEN25_7B_ARCH` and `"planner"` → `QWEN25_1_5B_ARCH`.~~ **CLOSED by
  M1-A, 2026-08-22:** both roles now map to `QWEN35_4B_ARCH`
  (`core/resource_gate.py:1040-1041`). Kept in this list as a closed
  entry so `NEW-156`'s cross-reference still resolves. It was the single
  highest-risk line item in the migration — a wrong arch silently
  produces a wrong KV term, the `NEW-84` class of admission-safety bug —
  and that risk is now retired for the *arch* side. One residue remains
  until M1-B: `utils/config.py` still points `MODEL_PATH` at the 7B file
  while `"primary"` costs with the 4B's arch, a 768MiB under-estimate in
  the unsafe direction, recorded as `NEW-161`.

  All bullets above are now closed — M1-F ran 2026-08-24. **Update
  2026-08-25: code-reviewer-approved.** The mandatory CLAUDE.md rule-4
  pass ran in a follow-up session — independently re-derived both
  constants' byte arithmetic against a fresh live `/proc/meminfo` read,
  independently confirmed the `compute_device_ceiling_bytes()` ordering
  invariant, and reran the full test suite itself (661 passed, 1
  skipped, matching). Approved after one documentation-only fix
  (`PROJECT_LOG.md`'s "Files touched" line was missing
  `tests/test_loader_resource_gate.py`). Status: **code-complete,
  code-reviewer-approved, not live-verified** (still arithmetic
  re-derivation from M1-E's already-live data, not a fresh live pass — no
  live component by design). See `NEW-181` for a since-corrected
  transient status-tracking gap from this same round (commit `2eae89f`'s
  own message stated the review had happened while these tracked docs, at
  commit time, still said it hadn't — the review genuinely had happened,
  just not yet reflected here; this line is that correction).

---

## 6. The plan

Two tracks run in parallel, plus standing lanes that never close.
**Track A (platform)** unblocks anything needing a model. **Track B
(business)** is the Jan-1 deliverable. They intersect at exactly two
points, named below.

> ### ▶ Start here: M1, the model migration (§6.2)
>
> **Ish's direction, 2026-08-22: do the model change fully, before
> anything else on Track A.** Not after the review debt, not alongside
> other platform work — first.
>
> The reasoning is sound and worth stating so nobody re-sequences it
> later: every open item in Phase A1 is measured against whichever model
> is actually loaded. The pending live-verification pass, the two
> unreviewed rule-4 diffs, the stale budget constants, 7.4b's context
> ceilings, 7.3's tier thresholds — all of them are calibrated to models
> that are being retired. Doing any of that work first means doing it
> twice, and the second time would invalidate the first. Migrating first
> means everything downstream is measured once, against the model that
> will actually be there.
>
> The one thing that does **not** wait behind M1 is Track B (§6.3) — the
> Core's schema, API, and auth touch no model at all and can start in
> parallel today.

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

**Why first:** nothing that loads a model is safe until this is real.
Also unblocks §6.5's AI-assisted domain behavior.

**Reshaped by §1.4 (2026-08-22).** The one-model decision lands squarely
in the middle of this phase. What it removes, what it keeps, and what it
adds:

- **Removes:** the concurrent primary+planner admission case (`NEW-141`,
  `NEW-140` scenario 3, `NEW-142`'s planner-eviction path) — there is no
  pair left to run concurrently. 7.4b sub-task B (planner context
  ceiling) becomes moot: no separate planner model survives to cap.
- **Keeps, unchanged:** the lease/registry, the concurrency test, the
  gate mechanism itself. None depend on which model is loaded.
- **Adds:** the migration itself, **M1 below, which runs first.**

**Blocked-by: nothing.** M1 starts now. §4.4's review debt is **folded
into M1's own mandatory review pass** rather than gating it — M1 touches
the same files, so reviewing a superseded intermediate state first would
be wasted effort. The gate is re-pointed, not relaxed: see §4.4 for the
three conditions that keeps it honest (the reviewer brief must name the
two previously-unreviewed diffs; live-verification runs under the real
`codey-start` entry point; and if M1 slips, the debt reverts to
standalone).

#### M1 — migrate to Qwen3.5-4B as the single model ◀ START HERE

**Ish's direction, 2026-08-22: do the model change fully before anything
else on Track A.** Sub-tasks in dependency order. A/B/C/D/E all touch
model load/spawn paths, so **every one is CLAUDE.md rule 4 category** —
mandatory code-reviewer pass, no exceptions, including for the ones that
look like config edits.

- **M1-A — arch + cost correctness first, before anything loads.**
  **DONE 2026-08-22 — code-complete and code-reviewer-reviewed (one
  blocking finding, C-1, fixed and re-verified), landed as `a030bbf`; no
  live component by design (§4.2, Appendix A).** Landed
  as an optional `ModelArch.n_attention_layers=8` (NOT the `n_layers=8`
  route offered below — that stores a number disagreeing with the model's
  real layer count), plus a 4th `CostEstimate.recurrent_state_bytes`
  term; `QWEN3_4B_ARCH` was **re-scoped, not deleted** (renamed
  `QWEN3_4B_TEST_ARCH`; it is still load-bearing for the
  `CODEY_TEST_PRIMARY_ARCH` contract). The original statement of the
  sub-task is kept verbatim below as the record of what was asked for:

  Two things, and the second is the one that matters:
  1. Point `core/resource_gate.py`'s `KNOWN_MODEL_ARCHS` at a `qwen35`
     entry — **both roles, not just `"primary"`.** `"planner"` currently
     maps to `QWEN25_1_5B_ARCH`, and it stays a live role until M1-D
     collapses it (M1-B repoints the planner *model* at the same file, so
     from that moment a `"planner"` slot costed with a 1.5B's
     architecture is wrong). Leaving either is the `NEW-84` class of
     admission-safety bug — a silently wrong KV term. Also delete or
     re-scope the test-only `QWEN3_4B_ARCH` substitute (36 layers, 8 KV
     heads) — it describes the *older* Qwen3-4B and is now one confusable
     name away from the real default (rule 14).
  2. **`ModelArch` cannot express this model.** It assumes every layer
     attends; Qwen3.5-4B has 8 full-attention layers and 24 SSM layers
     (§1.4). Passing `n_layers=32` would over-estimate KV by ~4× and
     wrongly refuse `n_ctx=65536`, which §5.1 shows is affordable.
     Either add a hybrid field (e.g. `n_attention_layers`, derived as
     `block_count / full_attention_interval`) — the honest fix — or pass
     `n_layers=8` with a comment stating *exactly* why the number
     disagrees with the model's real layer count, so the next reader
     doesn't "correct" it back to 32. Whichever route, the constant's
     comment must record that this is a hybrid Transformer-SSM model and
     name the GGUF fields it was derived from (`NEW-157`).
  Unit-testable with synthetic meminfo; no model load.
- **M1-B — config repointing: EVERY model slot becomes Qwen3.5-4B.**
  **DONE 2026-08-23 — code-complete and code-reviewer-approved (two review
  passes, see §4.2); landed as `841ef2e`; no live
  component by design, M1-E covers that.** The original statement of the
  sub-task is kept verbatim below as the record of what was asked for.
  Ish's explicit instruction (2026-08-22): "make sure you do it for both
  models." After this sub-task, **no code path anywhere can load a
  Qwen2.5-Coder-7B or a Qwen2.5-Coder-1.5B**, including through an env
  var left set in a shell, a stale test fixture, or the LoRA swap path.
  In `utils/config.py`:
  - `MODEL_PATH` → `~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf`.
  - `PLANNER_MODEL_PATH` → **the same file.** Do not leave it pointed at
    the 1.5B "until M1-D removes it" — that is exactly how a retired
    model survives a migration. The planner *role* outlives this
    sub-task; the planner *model* does not.
  - `SECONDARY_MODEL_PATH` → the same file, or removed outright. It
    currently names the 1.5B and is read by `core/lora_import.py`'s swap
    path and `core/model_tiers.py`. Decide, don't leave it dangling.
  - Retire `get_planner_n_ctx()`'s 8192 ceiling as a *separate model's*
    budget (it was derived for a 1.5B). If a smaller planning context is
    still wanted, re-derive it for this model; do not carry the old
    number across.
  - Rename `QWEN_7B_MMAP`/`QWEN_7B_MLOCK` (misleading now; behavior
    unchanged).
  - Set the `n_ctx` default to **65536** — **decided by Ish, 2026-08-22
    (§8 Q1, answered).** 4.852GiB total / 6.065GiB required against the
    ~6.49GiB ceiling. Conditional on M1-A having landed (without it the
    gate over-estimates and refuses 65536) and subject to M1-E's
    measurement; a material disagreement goes back to Ish.
  - Grep for any remaining hardcoded path or `qwen2.5` string outside
    tests before calling this done, and check the environment for a set
    `CODEY_MODEL`/`CODEY_PLANNER_MODEL`/`CODEY_SECONDARY_MODEL` that
    would silently override all of the above.

  **Interim state between M1-B and M1-D, stated so it isn't a surprise:**
  with both slots on one file but the planner path still spawning its own
  server (port 8081), a planning call would load a **second copy of the
  same model** — correct, but wasteful (~3GiB for nothing) and pointless.
  Two acceptable ways through: land B and D together as one reviewed
  change, or land B and accept the interim only if D follows immediately.
  **Do not ship the interim as a resting state.** The gate will admit it
  (both copies fit), which is precisely why it needs saying — nothing
  will fail loudly to warn you.

  **Real consumers, enumerated by direct code read 2026-08-22 — this is
  the list, do not re-derive it from memory** (the discipline 7.4 used,
  and the reason `NEW-24` was found at two call sites rather than one):

  | File | What it uses |
  |---|---|
  | `core/planner_loader.py` | The whole module — `cfg.PLANNER_MODEL_PATH` (read fresh, `NEW-84` pattern), `PLANND_SERVER_PORT`, `cfg.get_planner_n_ctx()`, `load()`/`ensure_planner()`/`get_planner_loader()`/`reset_planner_loader()` |
  | `core/plannd.py` | `get_planner_loader().ensure_planner()` (line ~371), `PLANND_SERVER_PORT` (line ~388) |
  | `core/summarizer.py` | `PLANND_SERVER_PORT` as `_05B_PORT` — **summarization runs on the planner server too**, a second role that moves to the 4B; easy to miss |
  | `core/daemon.py` | Planner preload/watchdog: `get_planner_loader()`, `PLANND_SERVER_PORT` (lines ~490-507) |
  | `core/loader_v2.py` | `_evict_planner_and_confirm_free()` — imports `get_planner_loader`, probes `PLANND_SERVER_PORT` (lines ~968-978) |
  | `core/lora_import.py` | Mutates `cfg.PLANNER_MODEL_PATH` at four sites (~362, 397, 438, 530) and routes through `get_planner_loader()` (~365, 466) |
  | `core/model_tiers.py` | `MODEL_TIERS`' planner-role entries: `model_ref=str(cfg.PLANNER_MODEL_PATH)`, `port=cfg.PLANND_SERVER_PORT` (~100-102) |
  | `core/planner_service.py` | The fallback ladder's daemon-planner attempt, plus `classify_tier("coding", "planner", ...)` |
  | `core/resource_gate.py` | `KNOWN_MODEL_ARCHS["planner"]`, the `"planner"` slot role, and a `get_planner_n_ctx()` reference (~1278) |
  | `codeydOS` | `start_plannd()`/`stop_plannd()`, the port-8081 status line, the gate `register_slot(model_id="planner")` from `U.28`, and two `pkill -9 -f "llama-server.*8081"` calls (~261, ~407) |

  Plus the test suite, which pins much of this behavior — expect real
  test churn, and treat a test that has to be deleted rather than updated
  as a signal to re-read the sub-task, not a formality.
- **M1-C — pass `--jinja` and wire thinking mode** (`NEW-158`).
  **DONE 2026-08-23 — code-complete and code-reviewer-approved (two review
  passes, see §4.2); landed as `841ef2e`; no live
  component by design, M1-E covers that.** `NEW-162` (the `--help` text
  disagreeing with `NEW-158`'s framing) was resolved by dumping the actual
  GGUF chat template — thinking mode is off by default unless a caller
  opts in — but stays open/Suspected pending a live spawn. The original
  statement of the sub-task is kept verbatim below as the record of what
  was asked for.
  `core/loader_v2.py:_spawn_locked()` (~line 331) does not pass
  `--jinja` today, so the GGUF chat template and `enable_thinking` are
  inert. Add it, plus `--reasoning-format` so the server splits
  `<think>` content into `reasoning_content` rather than inlining it in
  the reply. Then make planning requests opt in via
  `chat_template_kwargs: {"enable_thinking": true}`. **Verify the flag
  actually changes behavior before building on it** — the binary carries
  the strings, which is evidence it supports them, not proof.
- **M1-D — collapse the planner onto the one server.** **DONE
  2026-08-23 — code-complete and code-reviewer-approved (two review
  passes, the first of which required a fix in `core/lora_import.py`'s
  swap-symmetry, since applied and re-reviewed; see §4.2); NOT YET
  COMMITTED as of this writing; no live component by design, M1-E covers
  that.** This is what
  makes "one model" real rather than "one model file loaded twice."
  `core/plannd.py`'s `get_plan()` calls
  `core/planner_loader.py:ensure_planner()`, which spawns a second server
  on 8081. That whole path collapses into a thinking-mode request against
  the single primary server. The planner *role* survives — planning still
  happens, `classify_tier("coding", "planner", ...)` still means
  something, `core/summarizer.py` still summarizes — it just stops having
  its own process, its own port, and its own model. `parse_steps()` must
  read the answer, never the reasoning — confirm what it receives once
  `--reasoning-format` is set. `codeydOS`'s `start_plannd()`/
  `stop_plannd()` go away with it, which **also retires two of the three
  open rule-3 `pkill` violations** (`NEW-99`, `NEW-103`) for free — check
  that they are genuinely gone rather than moved. Keep the gate's
  `"planner"` slot accounting honest: with no planner process, those
  registrations should disappear, not linger (`NEW-100`, `NEW-101`).
- **M1-E — live verification.** **DONE 2026-08-23 — fully live-verified**
  on real device via `main.py --no-resume` (deliberately not the full
  `codey-start`, since daemon+GUI would have consumed headroom this
  device didn't have to spare that session — but it routes through the
  identical `core/loader_v2.py:_spawn_locked()` code path, so the
  migration's own spawn logic was genuinely exercised). Rule 2 discipline
  followed: `free -h` recorded before (5.3Gi available) and after
  (6.7Gi available), three load/unload cycles, each PID individually
  tracked and killed (never `pkill -f`), confirmed fully unloaded between
  and after each (`ps aux | grep llama-server` clean).
  Real RSS across three spawns at `n_ctx=65536`: 5.19GiB, 5.1645GiB,
  5.3431GiB, 4.9476GiB — 2-10% above M1-A's 4.8518GiB estimate, well
  inside the ×1.25 headroom factor. **Closes `NEW-157`** with
  measurement — the hybrid-arch fix is confirmed directionally and
  quantitatively correct. A real non-thinking inference request returned
  coherent output (177.9s/124 tok, 135.7s/578 tok). A real thinking-mode
  planning request confirmed `reasoning_content` genuinely splits from
  `content` in the response — **closes `NEW-158` and `NEW-162`** (the
  latter with a caveat: no code-level A/B of flags-present-vs-absent was
  feasible since the flags are hardcoded, not env-toggleable, but the
  response-shape evidence is enough to confirm the flags are not no-ops).
  A real jinja2 render of the actual 7,816-char chat template against
  both `enable_thinking` states, plus a real coding-path request, showed
  no vision-namespace leakage — **closes `NEW-160`** (upgraded from
  Suspected to Confirmed-and-closed). **Left open, not confirmed either
  way:** whether `--flash-attn on` is actually active — the confirming
  llama.cpp log line never appeared at this build's default log
  verbosity; needs a higher-verbosity spawn or a different check.
  **Two new live findings, `NEW-164` and `NEW-165`** (see
  `NEW_ISSUES.md`): `PLANNER_MAX_TOKENS=1024` is confirmed too small for
  real thinking-mode reasoning on this device (the trace alone consumed
  the full budget on a real request, returning empty `content`, silently
  degrading planning to unplanned execution); and `get_plan()`'s
  hardcoded `timeout=60` is shorter than this device's real
  prompt-processing time for the planner's prompt, an independent and
  earlier-firing failure mode. Both open, unfixed as of this M1-E entry,
  **since fixed and live-verified as M1-E-fix, `4cbf9a8`, 2026-08-23**
  (see Appendix A's M1-E-fix entry), recommended as one
  bundled fix task run **before** M1-F/M1-G (see §4.2 for the full
  writeup and the reasoning for that ordering).
- **M1-G — prompts: re-check, don't pre-emptively rewrite.** Ish's own
  framing was "maybe we have to adjust our system prompts maybe not," and
  that is the right posture — this is a measurement question, not a
  redesign. Three concrete things to check against the new model rather
  than assume:
  1. `prompts/system_prompt.py`'s tool-calling format. It was tuned
     against Qwen2.5-Coder-7B through several live rounds (the `NEW-30`
     read-before-patch fix was won at 3/3 vs 0/3). A different model
     family can regress that. **Re-run the existing A/B fixtures before
     changing a word of it** — this project has a working method for
     that; use it rather than editing on instinct.
  2. `core/plannd.py`'s `PLANNER_PROMPT` (~2,446 tokens) was written to
     compensate for a 1.5B model's limitations — heavy rules, worked
     examples, explicit format scaffolding. A 4B model reasoning in
     thinking mode plausibly needs much less of that, and the worked
     examples are themselves an open bug (`NEW-50`: example content
     leaks verbatim into unrelated requests). **This is the one prompt
     with a real case for shrinking**, but only after the thinking-mode
     path works end to end — measure first.
  3. `--jinja` changes prompt formatting for the existing coding path too
     (`NEW-158`): the server starts using the model's own template
     instead of its built-in guess. That is a behavior change to verify,
     not a free addition.
  - **2026-08-25 scoping update (desk only, no model loaded, thinking-mode
    now works via M1-E-fix so this item is now unblocked):** item 3's
    vision-namespace-leakage risk is already closed by M1-E's real jinja
    render + real coding-path request (`NEW-160`); the residual —
    does the jinja-rendered template still let `system_prompt.py`'s
    tool-calling instructions land intact for the specific
    read-before-patch case — is folded into item 1's live re-test rather
    than tested separately. Pre-registered test plan (not yet run — needs
    a live-verifier session):
    - **G1 (desk, done this round):** confirmed `prompts/system_prompt.py`
      at HEAD is byte-identical to the 2026-07-31 round's
      `.live_verify_scratch/system_prompt.FIXED.py` (the `NEW-30` fix is
      the committed baseline, not drifted) and that
      `.live_verify_scratch/fixture_b_small.py` resolves inside
      `WORKSPACE_ROOT` (`= Path(os.getcwd()).resolve()` in
      `utils/config.py`) when run with cwd at the repo root — the
      `NEW-60` workspace-boundary bug that invalidated two earlier `NEW-30`
      passes does not apply to this fixture as-is. Also confirmed
      `PLANNER_PROMPT` at HEAD (`edc9e36`) still contains the fibonacci
      worked example `NEW-50` traced as its exact leak source
      (`core/plannd.py:137-149`) — unchanged since the finding, so
      `NEW-50`'s "still reproduces on Qwen3.5-4B?" is a genuinely open
      question, not one already answered by the migration.
    - **G2 (one live cycle, item 1 + item 3's residual):** re-run the
      `NEW-30` read-before-patch A/B against Qwen3.5-4B using the existing
      `fixture_b_small.py`, same edit-only prompt shape as the 2026-07-31
      pass, N=3 draws. Pass criterion: `read_file` called before
      `patch_file`, and `old_str` is grounded in what `read_file` actually
      returned (not a guessed value). If 3/3 holds, item 1 and item 3's
      residual close as **measured, no edit needed** — that is a valid
      outcome, not a shortfall.
    - **G3 (separate live cycle, item 2 / `NEW-50`):** re-run `NEW-50`'s
      exact original test prompt ("Fix the off-by-one error in the loop
      in `core/legacy_calc.py`") through `core/plannd.py:get_plan()`
      against Qwen3.5-4B thinking mode. Recommend N=5 draws (up from the
      original N=3) given the leak's originally-observed 1/3 frequency —
      state honestly in the writeup that even N=5 clean draws cannot
      exclude a residual leak rate below roughly that same order, per
      rule 5. Pass criterion: no verbatim content from any of
      `PLANNER_PROMPT`'s worked examples appears in the plan for this
      unrelated real request. **Measurement-channel caveat, must be
      pre-registered before drawing:** M1-E confirmed Qwen3.5-4B returns
      its thinking trace in a separate `reasoning_content` field, not
      inline `<think>` tags — `parse_steps()`'s `<think>` strip
      (`core/plannd.py:201`) is a no-op on this model's response shape.
      Capture and archive **both** `content` and `reasoning_content` from
      the raw HTTP response for every draw. Score the pass/fail criterion
      against `content` only (that is what actually reaches the plan and
      the executor); record any leak appearing only in `reasoning_content`
      separately as observational, not a pass or a fail — the two
      outcomes ("leak fixed" vs. "leak relocated into the trace, plan
      still clean") are different findings and this is the only point at
      which they can still be told apart.
    - **Precondition gate (G2 and G3, before any inference is spent):**
      the harness must print the resolved `fixture_b_small.py` path and
      the resolved `WORKSPACE_ROOT` and abort on mismatch — this is the
      exact gate the 2026-07-31 third `NEW-30` pass added after `NEW-60`
      invalidated two earlier passes on precisely this failure mode. Do
      not treat G1's desk-only path check as sufficient on its own.
    - **G4 (conditional, only if G3 reproduces the leak):** prompt-engineer
      scopes the shrink referenced in item 2 — not attempted this round,
      since `NEW-50` may simply not reproduce on the new model's better
      instruction-following, and editing before measuring is exactly what
      this item warns against.
    - Explicitly out of this round's scope: `prompts/layered_prompt.py`
      and `prompts/critique_prompts.py` were read for orientation but are
      not named in the M1-G plan line; any finding in them would be a new
      `NEW_ISSUES.md` entry, not folded into this item.
    - **Status, 2026-08-25 (G2/G3 live cycles run):** G1 done (prior
      round). **G2 split, not a clean pass.** Precondition gate passed;
      RAM discipline followed (PID 31329, killed directly, confirmed
      gone). Grounding: **3/3** — every `patch_file`'s `old_str` matched
      real file content, zero hallucination. Sequencing (read-before-
      patch): **1/3, and the criterion turned out unmeasurable with this
      harness** — `core/context.py:97`'s `auto_load_from_prompt()`
      auto-preloads any file named in a bare task prompt into working
      memory *before* the model runs (`✓ Loaded: fixture_b_small.py (432
      chars)` in every draw's pre-inference log), so draws 1-2 had no
      need to call `read_file` themselves; this isn't a discipline
      failure, it's a confound in this specific prompt shape. **Item 1
      and item 3's residual do NOT close on this result** — see
      `NEW-182` for the full trace, including direct confirmation that
      the *original* 2026-07-31 `NEW-30` A/B pass (`ab_driver.py`'s
      daemon-step-template `case1_prompt`, 3 draws per arm — verified
      this is the actual A/B script, not `driver.py`'s separate
      single-draw trials) was NOT subject to this same confound (no
      `✓ Loaded:` line in `ab_output.log`, explicit `read_file` calls in
      all 3 fixed-arm draws), so that earlier fix stands without a rule-6
      downgrade. **G2b as first proposed (re-run `case1_prompt` verbatim,
      on the theory that this shape avoids the preload) is NOT viable —
      corrected in the same pass that found it.** The reason the old run
      escaped the preload is `NEW-62`, a regex fix landed the *same day*
      (`4625e43`): the pre-fix `detect_filenames()` regex matched
      `.live_verify_scratch/case1_anchor.py` but stripped its leading dot,
      producing a path that then failed the existence check and got
      silently dropped — so nothing preloaded. The post-fix regex at HEAD
      resolves the same path correctly; a direct call to
      `auto_load_from_prompt()` on the identical `case1_prompt` text today
      prints `✓ Loaded: case1_anchor.py (151 chars)`. The `used < total *
      0.5` gate (`core/agent.py:1263-1264`) was checked directly too and
      evaluates `True` today (3759/65536) — not the blocker either. **Net:
      re-running `case1_prompt` verbatim today would hit the identical
      confound as G2, not avoid it.** A viable G2b needs a different
      design — a prompt referring to the target file in a form
      `detect_filenames()` won't match, or an explicit, honestly-labeled
      harness-side bypass of the preload for that one call — **not
      designed this round; flagged as the open next step (`NEW-182`).**
      Verbatim G2 data archived at
      `.live_verify_scratch/m1g_g2_results.jsonl`,
      `.live_verify_scratch/m1g_g2_output.log`,
      `.live_verify_scratch/m1g_g2_output_23.log`.
      **G3 clean 5/5, with the rule-5 caveat stated honestly.**
      Precondition gate passed; RAM discipline followed (PID 30582,
      `loader.unload()`, confirmed via `get_pid()` returning `None` and
      an empty `ps aux | grep llama-server`). All 5 draws returned
      `content` byte-identical to the correct answer
      (`"1. Edit core/legacy_calc.py: fix the off-by-one error in the
      loop"`), with correct CREATE-vs-EDIT `reasoning_content` (582-798
      chars) and no verbatim leak from any `PLANNER_PROMPT` worked
      example in either channel (confirmed via direct grep of the
      archived JSONL, not a narrow fibonacci-only check). Non-circularity
      confirmed via `git log -L`: the VIOLATION block (`plannd.py:60-66`)
      and worked EXAMPLE (`plannd.py:171-177`) containing this exact test
      prompt's correct answer were added in `d674a0c` (2026-07-30),
      *before* `NEW-50` was filed (2026-07-31) using this same prompt —
      `NEW-50`'s own text records a 1/3 leak on the 1.5B model despite
      this counter-example already being live, so 5/5 clean here is real
      evidence, not circular reasoning. **Per rule 5, 5/5 clean is "not
      reproduced in this sample," not "fixed"** — it cannot rule out a
      residual leak rate on the order of the original ~1/3. **Real
      methodological caveat for any future re-test:** this exact prompt's
      correct answer is now embedded verbatim twice in `PLANNER_PROMPT`
      (see `NEW-183`), which weakens it as a discriminator going forward;
      a fresh, non-overlapping prompt would be a stronger test if this
      concern needs re-checking later. The pre-existing `[plannd] plan
      may be truncated` false-positive fired on all 5 draws despite
      correct, complete plans — this is the already-tracked `NEW-168`
      bug (fenced to `NEW-173`), not new. Verbatim G3 data archived at
      `.live_verify_scratch/m1g_g3_results.jsonl`,
      `.live_verify_scratch/m1g_g3_output.log`.
      **G4 not needed** — no leak reproduced in `content` this round.
      **M1-G is NOT done.** Current state: G1 done, G2 needs a redo via a
      redesigned G2b (not yet designed — see `NEW-182`, the originally-
      proposed `case1_prompt` re-run was checked and found not viable at
      HEAD), G3 closed (with the stated rule-5 caveat), G4 not needed.
      Designing and running a viable G2b is the next concrete step,
      deferred to a future round rather than done in this docs-processing
      pass.
    - **G2b (re-designed, not yet run) — 2026-08-25, desk-only scoping
      round, no model loaded.** `core/context.py`'s `detect_filenames()`
      regex (`core/context.py:189`) requires the target's extension to
      literally be one of `py|json|js|ts|sh|yaml|yml|toml|txt|md|html|css|
      cpp|c|h|rs|go|rb|java` — for a real `.py` file (a full-match
      extension, not a prefix of a longer one), **no natural phrasing
      that names the file by path avoids the preload**: the regex matches
      the filename in any syntactic position, so referring to a `.py`
      target without triggering it and without resorting to vague,
      ambiguous natural-language description (a different, worse confound
      — the model would then have to guess the exact filename) is not
      achievable at HEAD. The only deterministic route is a fixture whose
      extension is not in that list. **Confirmed empirically** (not by
      regex reasoning alone, per rule 12) with the exact fixture and
      prompt below: `context.detect_filenames(PROMPT)` → `[]`, and
      `context.auto_load_from_prompt(PROMPT)` on a freshly-cleared
      `_mem` → `[]` with zero `_mem.list_files()` entries afterward.
      **Load-bearing subtlety, not a coincidence to skip re-verifying:**
      `re.findall` on this exact prompt actually returns one raw match —
      `.live_verify_scratch/case_g2b_anchor.c` (the regex tries `cpp`
      first, fails, then tries the shorter alternative `c` and succeeds,
      silently truncating `.cfg` → `.c`). The reason nothing preloads is
      `detect_filenames()`'s existence check: `case_g2b_anchor.c` does not
      exist on disk, only `case_g2b_anchor.cfg` does. **This means the
      precondition gate below is the actual protection, not ceremony** —
      if a stray `case_g2b_anchor.c` file is ever created in
      `.live_verify_scratch/`, or if `detect_filenames()`'s truncation
      behavior is ever "fixed" to require an exact/full extension match,
      this design silently breaks (either re-introducing the preload
      confound, or in the stray-file case, silently preloading the
      *wrong* file's content). This truncation behavior itself generalizes
      beyond this one test — `.cfg`→`.c`, `.pyi`/`.pyx`→`.py`,
      `.tsx`→`.ts`, `.jsx`→`.js`, `.hpp`→`.h` are all silently truncated
      the same way — logged as **`NEW-185`, Confirmed** (see
      `NEW_ISSUES.md`), not fixed this round since fixing `context.py`
      is out of this task's scope.
      - **Fixture (create fresh before the live run — `.live_verify_scratch/`
        is gitignored, so it will not persist between sessions; already
        created once this round for the empirical check above and must be
        reset to this exact content before every draw):**
        `.live_verify_scratch/case_g2b_anchor.cfg`:
        ```
        # Small config file used for M1-G G2b anchor case (genuinely-unread-file Edit step).
        timeout=30
        retries=3
        ```
        The `=` has no surrounding spaces deliberately — a model that
        guesses the file's content from the prompt alone (which supplies
        both the old and new values, same as the original `case1_prompt`
        design) would naturally guess the more common `timeout = 30`
        form. A first `patch_file` call using that guessed, spaced form
        will fail (`[PATCH_FAILED] old_str not found`), turning "did it
        read first" from trace-inference into content-forced evidence
        rather than relying solely on tool-call ordering.
      - **Prompt (exact text, matching `ab_driver.py`'s `case1_prompt`
        daemon-step shape verbatim — same structure as the original,
        already-valid `NEW-30` A/B pass):**
        ```
        Previous context: Build a small config helper module.

        Your task (step 2/2): Edit .live_verify_scratch/case_g2b_anchor.cfg to change timeout's value from 30 to 60.

        Complete only this step.
        ```
      - **N = 3**, matching the original `NEW-30`/G2 methodology (no
        reason found to deviate).
      - **Precondition gate (must run and print output before any
        inference is spent; abort on any failure):**
        1. `Path(".live_verify_scratch/case_g2b_anchor.cfg").resolve()`
           is under `WORKSPACE_ROOT` (`utils.config.WORKSPACE_ROOT`) and
           the file exists with the exact content above — confirmed this
           round: `WORKSPACE_ROOT` = `/data/data/com.termux/files/home/
           Codey-OS`, fixture resolves to
           `/data/data/com.termux/files/home/Codey-OS/.live_verify_scratch/
           case_g2b_anchor.cfg`, inside workspace = `True`.
        2. `.live_verify_scratch/case_g2b_anchor.c` (note: no `fg`) does
           **not** exist. If it does, delete it or pick a different
           fixture stem — its existence would silently re-enable the
           preload via the truncation bug above.
        3. `context.detect_filenames(PROMPT)` (direct call, `PROMPT`
           being the exact text above) returns `[]`.
        4. With `_mem.clear()` called first, `context.auto_load_from_prompt
           (PROMPT)` returns `[]` and `_mem.list_files()` is empty
           afterward, and no `✓ Loaded:` line appears in the log.
        5. **Payload-level assertion, stronger than auditing individual
           code paths:** after `enrich_message()` / `build_recursive_prompt()`
           / `build_file_context_block()` all run (i.e. the actual
           assembled message(s) sent on the *first* inference call of the
           draw), assert the fixture's distinctive string `retries=3` does
           not appear anywhere in that payload. This also covers the
           `_SELF_REVIEW_KEYWORDS` injection path (confirmed this round:
           the chosen prompt text contains none of those keywords) and any
           other pre-inference injection this design didn't enumerate by
           name.
      - **Tool-call definitions (pre-registered to keep every draw
        gradable — the model has shell access, so "read" and "edit" must
        be defined before drawing, not decided per-draw):** a **read** of
        the fixture is any of: a `read_file` call on the fixture path, or
        an `execute_shell`/equivalent call whose command reads the
        fixture's real content (e.g. `cat`, `head`, `sed -n`, `grep` on
        that exact path). An **edit** of the fixture is any of: a
        `patch_file` or `write_file` call targeting the fixture path, or
        an `execute_shell` call that mutates it (e.g. `sed -i`, `echo >`,
        `echo >>`, `tee`). A draw with neither a qualifying read nor edit
        before the step budget/step-count runs out is a hard FAIL on both
        axes, not an exclusion.
      - **Grading, per draw (report as two fractions, X/3 and Y/3 — do
        not collapse into one number, matching G2's own reporting style):**
        - **Grounding:** scored on the **first** edit-tool call only (a
          later successful edit after a `[PATCH_FAILED]` retry-with-full-
          content does not retroactively make the first guess "grounded" —
          this ambiguity exists in `patch_tools.py:44-55`'s retry-with-
          full-content behavior and must not be allowed to blur the
          measurement). PASS if that first edit's `old_str` (or, for
          `write_file`, its full new content) is an exact substring of
          the fixture's real on-disk content at that moment. FAIL if it
          is a guessed/reconstructed value that doesn't match.
        - **Sequencing:** PASS if a qualifying read (per the tool-call
          definitions above) targeting the fixture appears anywhere in the
          trace **before** the first qualifying edit targeting it. FAIL if
          any edit precedes any read, regardless of what happens after —
          a late corrective read after an already-issued edit does not
          rescue the draw.
      - **Overall verdict:** report grounding X/3 and sequencing Y/3
        separately; no single pass/fail declared for the round. Per rule
        5, even 3/3 on both axes is "not reproduced in this sample," not
        proof of a fixed behavior — state that explicitly in the writeup
        when this actually runs.
      - **Known limitation, stated honestly rather than left implicit:**
        this fixture is a `.cfg` file, not `.py` — the only reason a
        Python fixture can't be used here is `detect_filenames()`'s
        design (see above). A result on this fixture is evidence about
        the same *instruction* (read before editing) but under a
        different *fixture domain* than the 2026-07-31 `NEW-30` pass and
        G2's `fixture_b_small.py` attempt — it is not numerically
        comparable to either as an apples-to-apples re-run, only as an
        independent data point on the same underlying question. A `.pyi`
        fixture would evade the preload via the same truncation mechanism
        while staying Python-shaped, which would narrow this gap somewhat
        if a future round judges the domain difference is actually
        material — not adopted this round, since `.cfg` is simpler and
        the domain gap is disclosed rather than hidden.
      - **Not yet run** — this is a pre-registered design only, per this
        round's scope. No live-verifier session was invoked.
      - **2026-08-25, third round: G2b run live. Grounding 3/3, sequencing
        3/3, clean.** Precondition gate: all 5 parts passed, re-verified
        fresh this session (fixture recreated with exact spec content,
        `WORKSPACE_ROOT`/path resolution confirmed, no stray
        `case_g2b_anchor.c` sibling exists, `detect_filenames(PROMPT)` and
        `auto_load_from_prompt(PROMPT)` both returned `[]`, payload-level
        assertion passed — the fixture's `retries=3` content confirmed
        absent from the assembled pre-inference payload). RAM discipline:
        `free -h` before `5.6Gi used, 598Mi free, 4.9Gi available`, after
        `5.2Gi used, 2.9Gi free, 5.4Gi available`; `ps aux | grep
        llama-server` clean before and after; `loader.get_pid()` returned
        `None` after `loader.unload()`. **Deviation from spec, stated
        plainly:** the cycle was not one continuous server process —
        `core/thermal.py` fired mid-run and restarted the server (PID
        23098 at `-t 4` → thermal throttle → PID 31624 at `-t 2`), so two
        `llama-server` PIDs existed sequentially (never concurrently)
        within one tracked load-then-unload cycle; rule 2's "one live
        model-load cycle at a time" held, the spec's "no reload per draw"
        framing was violated by a real thermal artifact, not a driver
        choice. **Results, all 3 draws identical in shape:** draw 1 —
        `read_file(case_g2b_anchor.cfg)` → `patch_file(old_str=
        "timeout=30", new_str="timeout=60")` → `note_save` (called twice,
        duplicate, post-completion — see `NEW-186`); draw 2 — identical
        shape, also a duplicate `note_save`; draw 3 — identical shape,
        single `note_save`. On-disk file content after all 3 draws
        matched (`timeout=60`, `retries=3` — correct edit each time).
        Grounding 3/3: every `old_str` an exact substring of the fixture's
        real content at time of patch. Sequencing 3/3: a qualifying
        `read_file` on the fixture appears before the first qualifying
        `patch_file` in every draw's trace order. Direct proof the preload
        was absent *during* the actual run, not just predicted pre-flight:
        the `✓ Loaded: case_g2b_anchor.cfg` marker (the signature that
        appeared *before* inference in the original failed G2 attempt) is
        absent in all 3 draws; the only load-adjacent marker is `ℹ Read
        .live_verify_scratch/case_g2b_anchor.cfg (106 chars)`, which
        appears *after* the model's own `read_file` call in every draw.
        **Content-trap caveat, stated honestly:** the fixture's unspaced
        `timeout=30` was designed so a model that guessed instead of
        reading would likely emit the more natural `timeout = 30` and get
        a patch failure, making "did it read first" content-forced rather
        than purely ordering-inferred. This trap never fired — no draw
        ever produced a failed patch attempt — so the sequencing result
        rests on tool-call trace order plus the precondition gate's own
        payload-level confirmation that the fixture's real content
        (`retries=3`) was absent from the pre-inference payload (making
        trace order meaningful rather than purely circumstantial), but it
        is still weaker corroboration than a caught bad guess would have
        given — record this as such, not as fully content-forced evidence.
        **Scorer self-correction, per rule 6:** the live run's own
        in-process scorer had a regex bug (required a closing `</tool>`
        tag the model's streamed output never emits) that made the first
        pass's output log incorrectly show all 3 draws as FAIL. Caught
        in-session, the same already-captured stdout was re-parsed with a
        corrected regex (no new inference, no new model load), confirming
        11 raw `<tool>` markers all parsed with 0 JSON errors. **Re-run
        gotcha, since `.live_verify_scratch/` is gitignored and this fix
        will not survive the session:** any future re-implementation of
        this scorer must not require a closing `</tool>` tag — the model's
        streamed tool-call output does not emit one. **Latency gotcha, also
        won't survive in the gitignored logs:** device thermal throttling
        made draw 3 take 560.9s total (vs. the ~20-30s seen in G2/G3's
        earlier passes) — a real device artifact, not a hang; a future
        re-run with a ~20-30s latency expectation would misread a
        throttled draw as stuck. **What this can and cannot conclude, per
        rule 5:** 3/3 grounding + 3/3 sequencing is "not reproduced as a
        failure in this small sample," not "read-before-patch is fixed"
        for every domain. It rests on N=3, a single fixture domain (`.cfg`,
        which happens to avoid `detect_filenames()`'s extension match per
        `NEW-185`'s truncation bug, not because the underlying preload
        mechanism was fixed), and the content-trap's corroboration never
        actually firing. This narrows `NEW-182` from "unmeasurable" to
        "measurable and clean on one data point" — it does **not** close
        `NEW-182`, since the preload mechanism for `.py`/`.json`/etc. real
        target files is completely unchanged and still confounds any test
        using those extensions. Other findings from this run, not fixed:
        duplicate post-completion `note_save` calls on 2/3 draws, logged
        as `NEW-186` (Suspected-only link to `NEW-168`/`NEW-173`, not
        confirmed); direct confirmation the daemon/background
        `n_ctx=16384` context branch (7.4b item C) was correctly in effect
        for `TaskExecutor._execute_task`, as expected. Verbatim data:
        `.live_verify_scratch/m1g_g2b_output.log` (left in place,
        uncorrected, as an honest record of the scorer bug — not the
        source of truth), `.live_verify_scratch/m1g_g2b_regrade.log` (the
        actual scoring evidence, post-fix).
      - **M1-G overall status — DONE, 2026-08-25.** This is an
        architect-level judgment call on top of pre-registered
        measurements, not a pre-registered pass/fail the spec itself
        declared (the spec explicitly said "report grounding X/3 and
        sequencing Y/3 separately; no single pass/fail declared"). G1
        (desk, confirms the `NEW-30` fix is the committed baseline) + G2
        (live, grounding 3/3 in the real `.py`-under-preload domain — the
        one axis still live there, since sequencing is moot once content
        is already preloaded) + G2b (live, grounding 3/3 and sequencing
        3/3 in a genuinely no-preload `.cfg` domain) together give item 1
        and item 3's residual a real, if narrow, positive measurement on
        both applicable axes in their respective domains. Item 2 (`NEW-50`)
        closed via G3's clean 5/5 with the stated rule-5 caveat. G4 was
        not needed (no leak reproduced). **The one genuine residual —
        `.py`/`.json`-domain read-before-patch *sequencing* specifically
        (as opposed to grounding, which G2 already measured there) —
        stays open as `NEW-182`, a standing methodology-gap finding, not
        as a blocker on M1-G itself: there is no reachable exit criterion
        for it at HEAD short of fixing `core/context.py`'s preload
        behavior (explicitly out of M1-G's scope, and itself
        `NEW-182`/`NEW-185` work) or building an explicit harness-side
        preload bypass (considered and deprioritized in this same
        section's G2b design notes). Holding M1-G open indefinitely for a
        test design that cannot be run at HEAD is worse doc hygiene than
        closing it with this residual scope stated plainly.** No edit to
        `prompts/system_prompt.py`, `core/plannd.py`'s `PLANNER_PROMPT`,
        or the `--jinja`/`--reasoning-format` spawn flags was made or is
        warranted by this round's measurements — "measured, no edit
        needed" is itself the valid outcome Ish's own framing
        anticipated. Confirmed nothing downstream in §6.2's Phase A1
        ordering (7.4/7.4a/7.4b remnants, the lease/registry, the
        concurrency test) assumed a prompt edit would land as a
        precondition — none do; that ordering is unaffected by this
        close.
- **M1-F — re-derive the stale constants** (`NEW-156`) — **DONE
  2026-08-24, code-complete, code-reviewer-approved 2026-08-25,
  not live-verified** (arithmetic re-derivation from M1-E's already-live
  data, no live component by design). `MAX_CONCURRENT_MODEL_BUDGET_BYTES`: 8.90GiB →
  7.00GiB. `MAX_SWAP_ASSIST_BYTES`: 10.00GiB → 6.50GiB. Both computed via
  this project's own `estimate_model_load_cost()`/
  `compute_swap_assisted_headroom_bytes()` against the real on-disk
  primary/embed files and a fresh live `/proc/meminfo` read (2026-08-24
  session), per rule 5 — not reused from M1-E's earlier session numbers.
  One real finding from this round, not assumed: M1-F's own first-pass
  concurrent-budget value (5.25GiB, derived from the concurrent raw sum
  alone) sat below `compute_device_ceiling_bytes()` and was caught
  immediately by the project's own existing single-model tests, surfacing
  a previously undocumented, untested ordering requirement between the
  two constants (`NEW-179`, fixed same round with a new regression test).
  Also spun off `NEW-180` (embed model's real resident RSS still
  unmeasured — both re-derived constants still use the same file-size
  floor estimate every prior derivation used, not currently load-bearing
  at the new margins but never checked against reality). Full derivation
  in `core/resource_gate.py`'s own comments on both constants; test
  suite run (`tests/`, 661 passed, 1 skipped) passes in full. **Not live-verified —
  this round is arithmetic re-derivation from M1-E's already-live
  measurements, not a fresh live pass of its own, consistent with this
  task's own scoping (M1-F "waits on M1-E," not a live-verify step
  itself).** Mandatory code-reviewer pass (rule 4, this category gates
  model-load admission) still needs to run before this is fully done —
  no code-reviewer subagent was available in this session.
- **Status update, 2026-08-25 (later same day) — mandatory rule-4
  code-reviewer pass on `NEW-135`/`NEW-136`'s fix (commits `3513661`/
  `f7511bb`): APPROVED, no changes required.** Reviewer independently
  confirmed: lock coverage complete (the swap-claim sum sits inside
  `reserve_slot()`'s existing lock, mirroring the pre-existing RAM-side
  `reserved_bytes` pattern); the `can_dispatch_task()` gap is honestly
  disclosed, not hidden, and judged an acceptable disclosed limitation
  rather than a blocking defect — now separately tracked as `NEW-187`
  (open) per rule 8, rather than left as prose only; no leak on slot
  release; no double-counting between the RAM and swap accounting axes;
  the `test_new135_..._wiring_actually_uses_persisted_pending_claim`
  regression test was independently re-verified (reviewer hand-reverted
  the wiring line and reran, confirming it fails without the fix); full
  suite independently rerun, 669 passed/1 skipped, matching the
  implementing session's count exactly; the existing `NEW_ISSUES.md`/
  this document's update language was checked against the actual diff
  and found accurate. **`NEW-135`/`NEW-136` are now FIXED and
  code-reviewer-approved; not live-verified (no live component by
  design — admission-accounting logic, not a model-load test).**
  **7.4a is not yet fully closed by this**: `NEW-187` (the
  `can_dispatch_task()` gap, newly tracked) and `NEW-140`'s remaining
  model-independent content (the general swap-assist-re-admits-distress
  mechanism, unaffected by this round's `NEW-140`-scenario-3 closure)
  both stay open standing items.
- **Status update, 2026-08-26 — `NEW-187` fixed (one-directional,
  code-complete, NOT yet code-reviewer-approved); `NEW-140`'s remaining
  content re-measured and stays open, WORSE than the stale figures showed.
  7.4a STILL NOT CLOSEABLE.** `core/resource_gate.py`'s `can_dispatch_task()`
  now passes `total_reserved_swap_bytes()` — the exact `NEW-135` ledger,
  already documented as usable by "any direct caller that isn't
  `reserve_slot()`" — into `compute_swap_assisted_headroom_bytes()`'s
  `reserved_swap_bytes` parameter, so a dispatch decision's own 768MiB cap
  shrinks by whatever a concurrently-PENDING `reserve_slot()` admission has
  already claimed. This is deliberately one-directional (dispatch reads the
  ledger, never writes to it — `can_dispatch_task()` registers no slot and
  runs already-resident models, so it has no durable claim of its own to
  contribute), judged the correct closing shape for this specific gap, not
  a partial fix. Two new tests
  (`test_can_dispatch_task_new187_deducts_reserve_slot_pending_swap_claim`,
  `test_can_dispatch_task_new187_reserved_swap_read_failure_falls_back_to_zero`)
  added to `tests/test_resource_gate.py`; full suite **671 passed, 1
  skipped** (up from 669/1). **Per rule 4, this resource-gate admission-
  logic change has NOT yet had its mandatory code-reviewer pass — no
  subagent was available this session.** `NEW-140`'s remaining content was
  re-measured (desk-only, against already-recorded M1-E/M1-F real cost
  figures, no live model load) rather than left as an unmeasured standing
  concern: at the real Qwen3.5-4B interactive cost (5,209,547,936 bytes,
  4.8518GiB) and the current `MAX_SWAP_ASSIST_BYTES` (6.50GiB), the exact
  historical `NEW-21` fixture (`SwapTotal=8.0GiB, SwapFree=6.8GiB,
  MemTotal=10.8GiB, MemFree=2.2GiB`) now admits via `can_admit()` at ALL
  FOUR `MemAvailable` points in `NEW-21`'s own plausible range
  (2.2/3.5/5.0/6.5GiB) — including the 2.2GiB floor point that was the ONE
  denial left in the stale retired-7B worked example. See `NEW-188`
  (new) for the full re-derivation and real numbers. **Conclusion: does
  NOT close clean, does NOT close with an acceptable caveat — stays OPEN
  with an upgraded severity (4/4 admits, not 3/4), and the live low-swap-
  headroom single-model verification pass `NEW-140` originally called for
  has still never been run.** 7.4a's checkbox stays unchecked: one item
  needs a code-reviewer pass that hasn't happened, the other is a
  confirmed-and-worsened open concern, not a resolved one.
- **Status update, 2026-08-26 (later same day) — mandatory rule-4
  code-reviewer pass on `NEW-187`'s fix: CHANGES REQUESTED, then applied.**
  Reviewer found the read-failure fallback failed in the WRONG direction:
  `reserved_swap_for_dispatch = 0` on an unreadable ledger treats the
  failure as "no other in-flight claims," the MORE permissive reading —
  backwards for a gate, and inconsistent with both the sibling
  `CODEY_SWAP_ASSIST_ADMISSION` handler in the same function (fails
  toward disabled) and `reserve_slot()`'s own fail-closed handling of the
  identical ledger. Given `NEW-188`'s same-round finding that the
  swap-distress admission margin already widened from 3-of-4 to 4-of-4,
  reviewer treated the wrong fail-safe direction as a real defect, not a
  low-priority nit. **Fixed**: except-branch now sets `swap_assist_
  enabled = False` (matching the sibling handler's pattern exactly)
  instead of substituting a permissive `0`. The corresponding test
  (`test_can_dispatch_task_new187_reserved_swap_read_failure_falls_back_
  to_zero`) was renamed to `..._fails_closed` and its assertions flipped
  to expect `allowed=False`/`dispatched_via_swap=False`. Reviewer also
  flagged the docstring's "reads, never writes" framing as inaccurate —
  `total_reserved_swap_bytes()`'s default `reap_dead=True` does mutate
  the shared slot store under lock (dead-PID reaping) — corrected to
  "never registers a durable claim, though its reaping side-effect does
  mutate the shared store." Full suite after the fix: **671 passed, 1
  skipped** (`tests/`, excluding the separate `tests/test_restoricon_
  core/` package). **`NEW-187` is now code-complete, incorporating the
  reviewer's required changes — a follow-up confirmatory pass on the
  corrected diff is still needed before 7.4a can close**, since applying
  a reviewer's own requested fix is not the same as an independent
  re-review of the result.
- **Status update, 2026-08-26 (confirmatory pass) — `NEW-187`: APPROVED,
  no further changes required.** Independent re-review confirmed: the
  except-branch now sets `swap_assist_enabled = False` on a read failure
  (no permissive `0` substitution anywhere); control flow is sound (two
  separate `if swap_assist_enabled:` blocks, no dead/unreachable
  reference, no `NameError` path); the renamed
  `test_can_dispatch_task_new187_reserved_swap_read_failure_fails_closed`
  genuinely exercises the real call site and asserts the safe outcome;
  the docstring/`NEW_ISSUES.md` wording correction is accurate. Test runs
  independently reproduced: `tests/test_resource_gate.py -q` → 200
  passed; `tests/ -q --ignore=tests/test_restoricon_core` → 671 passed, 1
  skipped. **`NEW-187` is now fixed and code-reviewer-approved; not
  live-verified (no live component by design).** This closes `NEW-187`'s
  own review chain only — `NEW-140`'s remaining content and `NEW-188`'s
  live-verification gap are untouched by this fix and keep 7.4a's
  checkbox unchecked.
- **7.4a leftovers — `NEW-135`/`NEW-136` fixed, `NEW-140` scenario 3 /
  `NEW-141` confirmed and closed — 2026-08-25, code-complete and
  self-tested, NOT yet mandatory-code-reviewer-approved (superseded by
  the status update immediately above — kept as the original record of
  what the fix itself contained).** Picked as the
  next item in this section's own "Then:" ordering after M1 (A-G) closed
  — the only remaining 7.4/7.4a/7.4b item that didn't require a live
  session this round couldn't run (7.4's and 7.4b A/C's remnants are
  live-verify-only; see the correction below). `core/resource_gate.py`:
  `compute_swap_assisted_headroom_bytes()` gained `reserved_swap_bytes`
  (subtracted from the policy cap `max_swap_usage_bytes`, not from live
  `SwapFree` — the swap hasn't actually been consumed yet by a still-
  PENDING admission); `can_admit()` threads it through; `GateDecision`
  gained `swap_bytes_claimed` (a magnitude, not just the existing
  `admitted_via_swap` boolean, since `NEW-135`'s fix needs something
  summable — this directly satisfies `NEW-136`'s own fix-direction note
  in the same change rather than as a second pass); `reserve_slot()` now
  computes the real PENDING-only sum of other slots' `swap_bytes_claimed`
  inside its own existing lock (mirroring the RAM-side `reserved`/
  `committed` sums it already computed there — same TOCTOU reasoning) and
  persists the admitted decision's own claim onto the new slot record. A
  new `total_reserved_swap_bytes()` mirrors `total_reserved_bytes()` for
  any direct `can_admit()` caller outside `reserve_slot()` (none exist
  today). Eight new regression tests in `tests/test_resource_gate.py`
  (`test_new135_*`), including one that reproduces the exact pre-fix
  double-admission and confirms it is now refused, and one
  (`..._wiring_actually_uses_persisted_pending_claim`) added after advisor
  review flagged the other six as only proving the underlying functions
  correct in isolation — that test pre-loads a PENDING slot's claim via
  `register_slot()` with no hand-fed `reserved_swap_bytes` and was
  confirmed to fail if `reserve_slot()`'s own
  `reserved_swap_bytes=reserved_swap` wiring line is deleted; full suite
  669 passed, 1 skipped (was 661/1 before this round). **Scope boundary, stated
  plainly:** this closes the race for `reserve_slot()`/`can_admit()`
  callers only — `can_dispatch_task()`'s separate swap-assist consumer
  (7.4a sub-task D2) registers no slot, so this accounting mechanism has
  nothing to sum against on that side; that residual is documented
  directly in `can_admit()`'s own docstring rather than silently left
  implicit. Separately, confirmed `NEW-140` scenario 3 and `NEW-141`
  directly against HEAD, each on its OWN correct evidence (not the same
  evidence applied to both, which would misdescribe scenario 3 — that
  scenario is single-model, not concurrent, so `core/planner_loader.py`'s
  absence isn't what closes it): `NEW-141` requires the retired concurrent
  primary+planner pair, and `core/planner_loader.py`/
  `_evict_planner_and_confirm_free()` are confirmed absent from HEAD —
  its reproduction path is structurally unreachable. `NEW-140` scenario 3
  describes the retired 7B's specific cost estimate under the old 10GiB
  cap at a single-model load; the correct evidence there is M1-B's already
  -confirmed repoint of every model-role path (`MODEL_PATH`,
  `PLANNER_MODEL_PATH`) onto Qwen3.5-4B, not the 7B — the single-model
  load this scenario describes cannot occur through any live production
  path today. Both close per `NEW-159`'s own stated bar (M1-D code-read +
  M1-E live pass, both already done). `NEW-140`'s other, model-independent
  content (the general swap-assist-re-admits-distress mechanism) stays
  open, unaffected by this closure. **Needs the mandatory rule-4 code-reviewer
  pass before this is fully done** — no code-reviewer subagent was
  available in this session, same limitation M1-F hit.
- **Correction to this document's own §6.2 table and Appendix A, 2026-08-25
  (rule 6):** both previously stated that 7.4b sub-tasks A and C "still
  need live-verify (M1-E)," as if M1-E already covered it or would as
  soon as it ran. **M1-E ran 2026-08-23 and did not cover this** — it
  deliberately used `main.py --no-resume` rather than the real
  `codey-start` entry point (see §4.2's M1-E entry for why: avoiding the
  daemon+GUI's extra headroom draw on a device that didn't have it to
  spare that session). 7.4b A (embed-always-resident) and C (interactive-
  vs-daemon context branching) specifically call for verification under
  the real `codey-start` entry point — a different, still-unrun check.
  Both remain genuinely open live-verifier asks, not items already
  quietly satisfied by a completed round.

#### Remaining Phase A1 items

| Item | State | What's left |
|---|---|---|
| **7.4** resource gate + slot-aware loader | 5/5 sub-tasks approved; core path live-verified | Re-target the pending production-config live pass at Qwen3.5-4B (M1-E covers it). The old `n_ctx=32768`-with-the-7B script is now obsolete — do not run it. **Re-checked 2026-08-26 against the same rule-6 concern raised for 7.4b's A/C rows: M1-E's own text states it ran via `main.py --no-resume`, "same `_spawn_locked()` code path as `codey-start`" — that phrase is the load-bearing distinction. 7.4's remaining ask is the resource-gate/loader admission path itself, which `_spawn_locked()` shares identically with `codey-start`; unlike 7.4b-A (embed residency across a full session's daemon lifecycle) and 7.4b-C (interactive-vs-daemon-dispatch branching, a daemon-specific code path), nothing about 7.4's ask depends on the daemon/GUI session wrapper `main.py --no-resume` skips. "Covered by M1-E" stands as written, not an inherited overclaim.** |
| **7.4a** swap-aware budget — **CLOSED 2026-08-26 (risk-acceptance decision, not a fix)** | A/B/C1/C2/D/F built and approved; E and G run | `NEW-135`/`NEW-136` (no `reserved_bytes` deduction on swap-assist; `admitted_via_swap` not persisted to the slot) — **FIXED 2026-08-25, code-complete, mandatory rule-4 code-reviewer pass APPROVED 2026-08-25 (same day, later review pass), not live-verified** (no live component by design — this is admission-accounting logic, not a model-load test). Reviewer independently confirmed lock coverage, no leak on release, no RAM/swap double-counting, and independently re-ran the `..._wiring_actually_uses_persisted_pending_claim` regression test by hand-reverting the fix (confirmed it fails without it); full suite independently rerun, 669 passed/1 skipped, matching the implementer's own count. See `NEW-135`/`NEW-136`'s own updated entries and `core/resource_gate.py` (`compute_swap_assisted_headroom_bytes()`'s `reserved_swap_bytes` param, `GateDecision.swap_bytes_claimed`, `reserve_slot()`'s new PENDING-swap sum, `total_reserved_swap_bytes()`). Fixed for the `reserve_slot()`/`can_admit()` path only — `can_dispatch_task()`'s separate swap-assist consumer (no slot registered, nothing to sum against) is explicitly NOT covered; reviewer treated this as an acceptable disclosed limitation, not a blocking defect, and it is now separately tracked as **`NEW-187`** (open) rather than left as prose only. `NEW-140` scenario 3 and `NEW-141` **confirmed and closed 2026-08-25**, each on its own correct evidence — `NEW-141` (concurrent case) on `core/planner_loader.py`'s confirmed absence from HEAD; `NEW-140` scenario 3 (single-model case, does NOT require `planner_loader.py`) on M1-B's confirmed repoint of every model-role path onto Qwen3.5-4B, since the retired 7B's specific cost figures no longer describe any live production path. `NEW-140`'s OTHER content (the general swap-assist-re-admits-distress mechanism, model-independent) stays open, unaffected by this closure. **7.4a is NOT yet fully closed**: `NEW-187` (new, open) and `NEW-140`'s remaining model-independent content (open, unaffected by this round) are both explicitly left standing rather than folded into this closure. **Status update, 2026-08-26**: `NEW-187` FIXED in `can_dispatch_task()` (reads `total_reserved_swap_bytes()`, one-directional per the fix's own scope — no durable claim of its own to contribute), 2 new tests, full suite 671 passed/1 skipped — **code-complete, mandatory rule-4 code-reviewer pass NOT yet run** (no subagent available this session). `NEW-140`'s remaining content re-measured against real Qwen3.5-4B cost (5,209,547,936 bytes) and current `MAX_SWAP_ASSIST_BYTES` (6.50GiB): the exact historical `NEW-21` fixture now admits at ALL FOUR `MemAvailable` points in its plausible range (2.2/3.5/5.0/6.5GiB), worse than the stale retired-7B figures' 3-of-4 — see **`NEW-188`** (new). Stays open, upgraded severity, not closed. **Status update, 2026-08-26 (confirmatory pass): `NEW-187` APPROVED** — a first review pass on the fix found the read-failure fallback failed in the permissive direction (`reserved_swap_for_dispatch = 0` instead of disabling the swap branch); fixed same round to match the sibling `CODEY_SWAP_ASSIST_ADMISSION` handler's fail-closed pattern, test renamed/flipped accordingly, docstring's "never writes" wording corrected (`total_reserved_swap_bytes()`'s `reap_dead=True` default does mutate the shared store); confirmatory re-review approved with no further changes, 671 passed/1 skipped independently reproduced. **`NEW-187`'s own review chain is now closed.** **Status update, 2026-08-26 (live-verification pass, natural-state-only per Ish's explicit scope choice)**: that previously-missing pass has now been run against real production `python3 main.py --no-resume`. Real `GateDecision`: `admitted=True admitted_via_swap=True swap_bytes_claimed=35,048,904` bytes, `estimated_cost_bytes=5,209,547,936` (matches `NEW-188`'s desk figure exactly); ambient `/proc/meminfo` at the moment of the call showed `MemAvailable=6.0321GiB` (unforced, ~35MiB below the 6.0647GiB required-cost threshold) but `SwapFree=14.415GiB` of 16.000GiB (90.1% free). Two-axis result: (a) swap-assist DOES activate live under real ambient conditions — CONFIRMED for the first time; (b) the compound low-RAM-AND-low-swap `NEW-21`-shaped distress state `NEW-140`/`NEW-188` are actually about — NOT reproduced, third consecutive live session finding this device's swap pool healthy. **7.4a's checkbox stays unchecked, residual narrowed**: pending only the compound-distress axis, not general swap-assist activation (now confirmed). Whether to pursue a deliberately-induced future pass or accept this as a standing documented risk is Ish's call — logged as §8 Q10. **Status update, 2026-08-26: Ish answered §8 Q10 — "accept the residual as a standing documented risk for now." 7.4a CLOSED on that decision, not on a fix or a live reproduction.** General swap-assist activation is confirmed live; the compound low-RAM+low-swap distress scenario was never observed live and is now accepted as a standing risk, not verified safe — see Appendix A's 7.4a entry and §8 Q10 for the full wording. |
| **7.4b** model lifecycle policy | Reshaped by §1.4 | **A**: embed always resident — implementation landed, code-reviewer pass done 2026-08-23 (§4.4). **LIVE-VERIFIED 2026-08-26 under the real `codey-start` entry point.** Real `codey-start` launch: embed `llama-server` (PID 31070) spawned immediately at daemon startup, before any coder request, and the SAME PID persisted through the coder's load and the subsequent 12-minute stall (`NEW-195`), including a severe RSS-eviction event (`NEW-180`) — the 96-line `~/.codeyOS/codeyOS.log` (spans `Daemon PID: 31066` through `Daemon stopped`, copy preserved at `docs/archive/live-evidence/2026-08-26-7.4b-codey-start/codeyOS.log`) shows no "Embed server died — restarting" line anywhere in that span. This item is now fully closed (code-complete, code-reviewer-approved, live-verified). **B**: planner ceiling 8192 — **moot, no separate planner**; note the correction below. **C**: coder interactive-vs-daemon context branching — landed + `NEW-152` fix, code-reviewer pass done 2026-08-23 (§4.4). **Status update, 2026-08-26 (clean(er) re-run, second live pass): BOTH halves now have real spawn-command-line evidence, closing the live-verification gap this row previously flagged — see the note below on why the parent item still does not close.** Interactive half: on-disk evidence is `~/.codeyOS/llama-server.log:1`'s spawn command line carrying `-c 65536` verbatim, corroborated by `ps`; genuine cold spawn against a clean pre-launch baseline. Background/daemon-dispatch half, tested for the first time this round: a task submitted directly via `core/state.py`'s real `StateStore.add_task()` (the same DB the daemon polls) was picked up with the daemon alone running (no TUI; `is_interactive_session_active()` returned `False`) and spawned `llama-server ... -c 16384 -t 6 ...`, matching `get_coder_background_n_ctx()` (`utils/config.py:137`) exactly; task completed (`status: done`), wall time 319s. **Neither half's spawn ordering exercised the specific race conditions `NEW-145`/`NEW-149`/`NEW-155` describe** (daemon-preload-wins-the-race, and whichever caller spawns first wins the context size for the server's life) — this round's interactive session loaded cold first, and the background test ran afterward against a restarted daemon, not in the interleaved orderings those three findings are about. **`NEW-145`/`NEW-149`/`NEW-155` stay open, unaffected by this round.** The original hang (`NEW-195`) did NOT recur on the same-scenario re-test this time (see `NEW-195`'s own entry for the full, deliberately non-overclaiming framing — this round changed two variables at once, `n_threads` 4→6 alongside the reduced confound, so it cannot be read as "confound proven, defect ruled out"). **C's live-verification-gap half now closes; C as a whole stays open** pending `NEW-145`/`NEW-149`/`NEW-155`'s underlying race conditions and the ceiling re-derivation noted below. **D**: folded into M1-F,
**DONE 2026-08-24** — the constant now reflects there being no separate
planner process, with real re-derived numbers. |
| **Lease/registry** | **Code-complete, mandatory rule-4 code-reviewer pass NOT yet run — 2026-08-26.** Replaced port-probe adoption with an explicit registry query, built directly against the existing resource-gate slot store rather than a second lease-file format. New: `find_resident_slot()` (query: is a model already resident, at what `n_ctx`/`pid`/`port`), `resolve_port_owner_pid()`/`_pid_owning_inode()`/`pid_cmdline_contains()`/`resolve_spawned_n_ctx()` (generalized from `embed_server.py`'s own pre-existing pattern, for positively identifying a genuinely-foreign process — never a name-based guess, rule 3), `register_slot()`/`reserve_slot()` now persist `n_ctx`. `core/loader_v2.py`'s new `_reconcile_adopted_slot()` registers a previously-unlisted resident coder server on adoption and logs (not respawns, per `NEW-149`'s own scope) an under-provisioned-ceiling mismatch. `core/embed_server.py`'s `start()` now adopts an already-healthy occupant instead of killing it (`NEW-146`'s actual fix — the daemon's own restart path, not just `core/inference.py`'s caller `NEW-144` covered), and `stop()`'s slot-release was moved out of the `if self.process:` block so an adopted server (no `Popen` handle, `self.process is None`) still releases its slot instead of leaking it — a leak this same round's own adoption fix would otherwise have introduced. 15 new tests (`tests/test_loader_resource_gate.py`, `tests/test_resource_gate.py`), full suite **692 passed, 1 skipped** (up from 671/1). **Real platform limitation found and documented, `NEW-200`**: `/proc/net/tcp`/`tcp6` are `PermissionError` on this actual device for every caller, including a process reading its own sockets — confirmed by direct read (rule 12), not assumed. This means `resolve_port_owner_pid()`'s primary path cannot succeed here for `NEW-104`'s original "truly foreign, no pre-existing slot" case; the mechanism degrades safely (returns `None`, never crashes, never falls back to a name-based kill) but is effectively non-functional on THIS device for that one sub-case — kept for portability to a rooted device or non-Android deployment. The two cases that DO work here (a slot this process itself registered; `embed_server.py`'s registered-slot fallback) don't depend on this scan. **Absorbs and updates**: `NEW-104` (partially — see `NEW-200`'s caveat), `NEW-144`/`NEW-146` (embed kill-and-replace of a healthy occupant, now fixed both at the `inference.py` caller AND the daemon's own `start()`/restart path), `NEW-149` (reuse-adopts-under-provisioned-server is now detectable/logged, not silently invisible — not auto-corrected, per this item's own scope). **Not yet reviewed**: this is rule-4 category (lock/process-lifecycle coordination) — the mandatory code-reviewer pass has not run. Do not consider this done until it does. |
| **Concurrency test** | Not started | Does `llama-server`'s slot/`--parallel` handling let one server serve the daemon, the TUI/GUI, and both limbs? No flag is set anywhere today. **Now the central question of this phase**, since one shared model is the whole architecture rather than one option in it. |

**Correction to this plan's own earlier claim, per rule 6:** the
2026-08-21 version of this document listed 7.4b sub-task B as "confirmed
by Ish, ready for implementer, not started." That was wrong — it is
implemented, as `get_planner_n_ctx()` in `utils/config.py`, and landed
inside commit `5687dcf` (the same commit `NEW-151` flagged for sweeping in
unreviewed work). The error came from trusting the archived `TODO.md`'s
sub-task status line rather than checking the code. It is moot under §1.4
either way, but the record should be accurate rather than conveniently
overtaken by events.

**Exit criteria:** Qwen3.5-4B loading through the gate at a chosen,
justified `n_ctx`, live-verified with verbatim byte figures; a
thinking-mode planning request producing a usable plan through the normal
planning path with no second model involved; the retired models' config,
process paths, and gate entries genuinely gone rather than dormant; the
constants in §5.1 re-derived from measurement; the lease/registry
replacing port probing; and the concurrency question answered with real
output.

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

**Status, 2026-08-26 — code-complete, mandatory rule-4 review run,
one blocking gap found and fixed, three (four, after the confirmatory
pass) non-blocking findings logged, NOT yet live-verified.**
`restoricon_core/` (`database.py`, `models.py`, `auth.py`,
`services/{audit_service,communication_service,crm_service}.py`,
`api/{server,routes}.py`) built: SQLite schema for all nine Appendix C
entities, PBKDF2-HMAC-SHA256 auth with the 7-role ladder (adds
`ai_agent` and `customer` to the 6 named above), append-only audit log
and communication history, and a `127.0.0.1`-bound REST API. Rule-4
review independently verified crypto, token handling, network binding,
parameterized SQL, audit-log append-only integrity, and SQLite
thread-safety all clean. **Blocking defect found and fixed same
day**: `crm_service.py`'s `get_project()`/`list_projects()` had no
`has_permission()` gate at all (`NEW-189`, proven with a fake
zero-permission actor, fixed and confirmatory-approved). **Non-blocking,
logged, not fixed**: `NEW-190` (silent `0.0.0.0` bind risk via env var),
`NEW-191` (500 handler leaks raw exception text), `NEW-192` (only
`admin`/`customer` can sign contracts — needs Ish's confirmation of the
real signing workflow), `NEW-193` (some entities have `POST` but no
`GET` routes yet), `NEW-194` (found during `NEW-189`'s confirmatory
pass: the narrowing logic below `NEW-189`'s new gate is still keyed on
`actor.role` identity rather than the permission that passed the gate —
same "one matrix edit away" latent shape as `NEW-189` itself, one layer
deeper). Test suite: `tests/test_restoricon_core/` 11 passed; full repo
suite 682 passed/1 skipped (includes an unrelated concurrent
`core/resource_gate.py` workstream's own tests). **Exit criteria not
yet fully met as "live-verified"**: the test suite includes live
HTTP client/server roundtrip tests, but this has not been confirmed
against the real `codey-start` entry point with a genuinely separate
OS process per rule 2/7's code-complete-vs-live-verified distinction —
that live-verifier pass is still open.
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
| **7.3 sub-task E** — actually dispatch on the tier decision | A1 | **DONE 2026-08-24.** Task A deleted the orphaned, unreachable `classify_tier()`/`planner_service.get_plan()` pair (`NEW-172`, landed `8fe5d07`). Task B built the real medium/hard split — tier decided once in `main.py` (`score.length > 300`), threaded as an additive/defaulted field through `_request_daemon_plan()` → `core/daemon.py`'s socket RPC → `plannd.get_plan(enable_thinking=...)`, with the client-side socket timeout deliberately pinned to hard-tier sizing regardless of tier (old-daemon safety) while the daemon's own internal timeouts scale per-tier. Code-reviewer-approved, code-complete. See Appendix A for the full design and `NEW-178` for the one known gap (the dormant pull-side planning path can't carry a tier value — bounded, that path has zero production callers today). |
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

1. ~~**`n_ctx` default for Qwen3.5-4B — 32768 or 65536?**~~ **ANSWERED by
   Ish, 2026-08-22: 65536.** Per §5.1 that is 2.553GiB file + 2.000GiB KV
   + 0.250GiB overhead + 50.25MiB SSM state = **4.852GiB total, 6.065GiB
   required at the ×1.25 factor, admissible against the ~6.49GiB
   ceiling.** The question had flipped from "how far down" to "how far
   up": with the 7B, 32768 needed ~7.95GiB of `MemAvailable`, a bar this
   device has never reached; with the hybrid 4B the same context costs
   3.852GiB and double it costs 4.852GiB (131072 is still a hard
   reject).

   **Two conditions travel with this decision and must stay stated,
   because 65536 is only affordable if both hold:**
   - **It depends on M1-A landing.** Under the old 32-layer assumption
     the gate over-estimates KV by ~4× (4 × 2.000 = 8.000GiB) and would
     refuse 65536 outright. The decision and the fix ship in that order.
     (M1-A landed 2026-08-22 as `a030bbf`; see §4.2.)
   - **It is still arithmetic.** M1-E measures real resident cost and is
     the check on it. If measurement disagrees materially with the
     4.852GiB estimate, that goes back to Ish rather than being silently
     absorbed.

   The actual edit is M1-B's, in `utils/config.py` — not M1-A's. Still
   downstream and still needing re-derivation against the new default:
   7.3's tier thresholds and 7.4b sub-task C's interactive/background
   ceilings, both sized against a model that no longer exists.
2. **The Core→device dispatch mechanism.** Reuse the existing Telegram
   Bot API channel the device app already polls, or build something
   Codey-OS-native? Not designed anywhere.
3. ~~**One model vs. swap scheduling.**~~ **Answered by Ish, 2026-08-22
   (§1.4): one model.** Qwen3.5-4B serves every role, with thinking mode
   in place of a separate planner. What remains from this question is not
   a decision but a test: whether one `llama-server` can serve several
   consumers concurrently (§6.2's concurrency test). Kept here, struck
   through, so the answer is visible rather than the question quietly
   vanishing.
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
8. ~~**Thinking-mode policy — when does the model think?**~~ **Answered
   by the 7.3 sub-task E work, 2026-08-24 (Task A + Task B, `8fe5d07` +
   `edc9e36`).** Gated on complexity, not always-on or TUI-triggered:
   `classify_tier()` (the option this question originally named as a
   log-only candidate) was deleted as dead code in Task A (`NEW-172`) and
   replaced in Task B by a real medium/hard split decided once in
   `main.py` (`score.length > 300`) and threaded through as
   `enable_thinking` all the way to `plannd.get_plan()`. Kept here,
   struck through, so the answer is visible rather than the question
   quietly vanishing, same pattern as Q3 above.
9. **Attribution-logging coverage.** Extend `core/recursive.py`'s
   attribution logging to `core/agent.py`'s separate plain-`infer()`
   branch as new work, or leave it as a documented accepted gap
   (`U.10`)?
10. ~~**`NEW-140`/`NEW-188`'s residual compound-distress gap.**~~
    **ANSWERED by Ish, 2026-08-26: "accept the residual as a standing
    documented risk for now."** Kept here, struck through, so the answer
    is visible rather than the question quietly vanishing, same pattern
    as Q1/Q3/Q8 above. A 2026-08-26
    natural-state-only live pass (Ish's own explicit scope choice for
    that round) confirmed swap-assist genuinely activates on the real
    device under real ambient conditions for the first time
    (`admitted_via_swap=True`, real production `reserve_slot()` call,
    `estimated_cost_bytes` matching `NEW-188`'s desk figure exactly) —
    but `SwapFree` was 90.1% free at the time, nowhere near the `NEW-21`
    fixture's compound low-RAM-AND-low-swap distress shape `NEW-140`/
    `NEW-188` actually worry about. This is the THIRD consecutive live
    session (after the two `NEW-137`/sub-task E sessions) in which this
    device's swap pool was found healthy during a real model load — never
    once naturally compound-distressed. The question: (a) authorize a
    future round to deliberately induce the compound low-RAM+low-swap
    state to test it directly, or (b) accept the residual as a standing,
    documented, low-probability-on-this-device risk and close 7.4a on
    that decision (per `NEW-141`'s own precedent, "close on the decision
    rather than on a fix")? Not a default either direction.

    **Resolution detail:** Ish chose option (b). **Resolved, not open.**
    This closes 7.4a — see its Appendix A entry and the §4 summary-table
    row for the exact scope of what "closed" means here. Stated plainly
    per rules 5/6 so it isn't misread later: this is a **risk-acceptance
    decision**, not a claim that the compound low-RAM-AND-low-swap
    `NEW-21`-shaped distress state was tested and found safe. It was
    never observed live across three consecutive real-device sessions,
    and the underlying arithmetic risk `NEW-140`/`NEW-188` documented
    (the exact `NEW-21` fixture now admits at all four plausible
    `MemAvailable` points under the current 6.50GiB swap-assist cap) is
    still real and undisputed — Ish's decision is to stop chasing a live
    reproduction of it on this device, not to declare it resolved by a
    fix. See `NEW-140`/`NEW-188`'s own entries in `NEW_ISSUES.md` for how
    each is now marked following this decision.

    **New evidence, 2026-08-26 (does not reopen this decision, logged
    for awareness per rule 8):** the very next live session (7.4b-A/C's
    `codey-start` live-verify pass) left a stale resident slot recording
    `swap_bytes_claimed=472,718,792` bytes — a value only set when
    `admitted_via_swap=True`, so a swap-assisted admission is inferred
    with high confidence, though the `GateDecision` line itself was not
    captured this session (unlike the previous pass, which captured it
    directly). ~13x the 35,048,904-byte claim that fed this resolution —
    under the
    tightest ambient `MemAvailable` (~1.8GiB) observed in any session so
    far, immediately followed by an unresolved 12-minute stall
    (`NEW-195`). `SwapFree` still never dropped below roughly 70% free
    during that session, so `NEW-21`/`NEW-140`/`NEW-188`'s specific
    low-RAM-AND-low-swap fixture shape was still not met — this is not a
    reproduction of the compound-distress condition Q10 was decided
    against, and this entry is not being reopened on that basis. **The
    stall's own cause is now separately in question** — `NEW-195` was
    corrected after capture once Ish reported the test device was
    concurrently handling an active phone call, other app use, and
    screen standby for the entire stall window, a confound unknown at
    capture time; the stall cannot currently be attributed to
    Codey-OS versus ordinary external resource contention. The
    swap-claim admission fact above is unaffected by that confound (it's
    a point-in-time resource-gate record, not a timing observation) and
    is recorded here on its own terms, because it is the closest any
    live session has come to the compound-distress shape yet — Ish
    should have it in view if this risk-acceptance is ever revisited.
    See `NEW-195` for the full detail and the corrected framing.

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

**▶ START HERE — M1: migrate to Qwen3.5-4B as the single model** (§1.4,
§6.2). Ish's direction 2026-08-22: do this fully before anything else on
Track A. Every other item in this phase is calibrated against a model
being retired, so doing them first means doing them twice. All of
A/B/C/D/E are rule-4 category; mandatory code-reviewer pass, and that
pass **also covers the two previously-unreviewed diffs** from §4.4.

- [x] **M1-A** — **DONE 2026-08-22, landed as `a030bbf`: code-complete
      and code-reviewer-reviewed (C-1 fixed and re-verified); no live
      component by design. Confirmatory sign-off folded into the
      M1-B/C/D brief — see §4.2's record-gap note.** `QWEN35_4B_ARCH` added
      and `KNOWN_MODEL_ARCHS` points **both** the `"primary"` and
      `"planner"` roles at it (dict still keyed by role, per `NEW-84` —
      deliberately not re-keyed by architecture). The 8/24 hybrid split is
      expressed as a new optional `ModelArch.n_attention_layers=8` rather
      than `n_layers=8`, so the retired archs stay byte-identical; the 24
      SSM layers' fixed state rides as a 4th `CostEstimate` term,
      `recurrent_state_bytes` = 52,690,944, derived from llama.cpp's own
      allocation code (`n_embd_r` + `n_embd_s` at F32 x 24 layers) after
      review caught a 26,935,296-byte under-estimate in the first pass —
      source-derived, still not measured, M1-E settles it. Verified total
      at 32768: 4,135,806,112 bytes = 3.852GiB, matching §5.1 exactly. `QWEN3_4B_ARCH` was **re-scoped,
      not deleted** — renamed `QWEN3_4B_TEST_ARCH` with a comment naming
      it as the *older* Qwen3-4B, because it is still wired into
      `_TEST_ARCH_REGISTRY_BY_ROLE` and the `CODEY_TEST_PRIMARY_ARCH`
      live-test contract and the model is still on disk (§6.2 authorizes
      "delete or re-scope"). Leaves `NEW-161` open until M1-B lands.
- [x] **M1-B** — **DONE 2026-08-23: code-complete and code-reviewer-
      approved (two review passes, see §4.2); landed as `841ef2e`.
      No live component by design; M1-E covers that.** Repointed **every**
      model slot in `utils/config.py` at the Qwen3.5-4B file: `MODEL_PATH`,
      `PLANNER_MODEL_PATH`; `SECONDARY_MODEL_PATH` removed outright as
      confirmed-dead code. Ish, 2026-08-22: "make sure you do it for both
      models" — satisfied, no path can load a 7B or 1.5B. Renamed
      `QWEN_7B_MMAP`/`QWEN_7B_MLOCK` to `QWEN_MMAP`/`QWEN_MLOCK`; `n_ctx`
      default set to **65536** (§8 Q1). Closes `NEW-161`. Landed together
      with M1-C/M1-D as one combined reviewed state, per this bullet's own
      "land with M1-D or immediately before it" guidance.
- [x] **M1-C** — **DONE 2026-08-23: code-complete and code-reviewer-
      approved (two review passes, see §4.2); landed as `841ef2e`.
      No live component by design; M1-E covers that.** Passed `--jinja` +
      `--reasoning-format deepseek` in `core/loader_v2.py:_spawn_locked()`.
      `NEW-160` and `NEW-162` remain open/Suspected — code-reviewer read
      the actual GGUF chat template (not `--help` text) and confirmed
      thinking mode is off by default absent an explicit
      `chat_template_kwargs` opt-in, so the coder/summarizer paths were
      never at risk from the new flags, but a live spawn is still the
      final word on both findings and neither closes here.
- [x] **M1-D** — **DONE 2026-08-23: code-complete and code-reviewer-
      approved (two review passes — the first returned CHANGES REQUESTED
      on a `core/lora_import.py` swap-symmetry fix, since applied and
      re-reviewed; see §4.2); landed as `841ef2e`. No live component
      by design; M1-E covers that.** Retired the second-server path:
      `core/planner_loader.py` deleted (322 lines);
      `core/loader_v2.py:_evict_planner_and_confirm_free()` deleted;
      `codeydOS`'s `start_plannd()`/`stop_plannd()` and the port-8081
      `pkill` sites all confirmed gone. Closes `NEW-142`, `NEW-100`,
      `NEW-101`, `NEW-124`, and the 8081 half of `NEW-99`/`NEW-103` (the
      8080-pattern `pkill` sites in `codeydOS` remain open under those
      same numbers). `NEW-137`, `NEW-140` scenario 3, `NEW-141`, `NEW-143`
      are code-read confirmed but stay open pending M1-E's live numbers,
      per `NEW-159`'s own disposition note. Surfaced a new pre-existing
      bug while fixing the lora_import swap-symmetry issue, logged as
      `NEW-163` (open/Suspected, out of scope to fix here).
- [x] **M1-E** — **DONE 2026-08-23, fully live-verified** on real device
      via `main.py --no-resume` (same `_spawn_locked()` code path as
      `codey-start`). Real RSS at `n_ctx=65536` across three cycles:
      5.19GiB, 5.1645GiB, 5.3431GiB, 4.9476GiB, all within the ×1.25
      headroom factor of M1-A's 4.8518GiB estimate — **closes `NEW-157`**
      with measurement. A real thinking-mode request confirmed
      `reasoning_content`/`content` genuinely split — **closes `NEW-158`
      and `NEW-162`** (latter with a no-code-level-A/B caveat, see §4.2).
      A real jinja2 render of the actual chat template plus a real
      coding-path request confirmed no vision-namespace leakage —
      **closes `NEW-160`**. Flash-attention activity for `qwen35` stays
      **unconfirmed** (the confirming log line never appeared at this
      build's default verbosity) — left open, not glossed over. Rule 2
      discipline followed throughout: `free -h` before/after, PID-tracked
      teardown, never `pkill -f`. Full findings and real latency numbers
      in §4.2. Surfaced two new live findings, **`NEW-164`** (planner
      token budget too small for real thinking-mode reasoning) and
      **`NEW-165`** (planner HTTP timeout shorter than real
      prompt-processing time) — both open, unfixed, see below.
- [x] **M1-E-fix** — **DONE 2026-08-23, landed as `4cbf9a8`, code-reviewer-
      approved (three separate passes) and live-verified for the
      scenarios tested.** Bundled `NEW-164` and `NEW-165`
      (`core/plannd.py:get_plan()`): `PLANNER_MAX_TOKENS` raised
      1024→2048 with a new `utils.logger` warning when a thinking-mode
      response comes back with empty `content` after
      `finish_reason=="length"` (`NEW-164`); the flat `timeout=60`
      replaced with `compute_planner_timeout()`, a formula derived from
      measured device rates, with `core/daemon.py`'s two outer
      `asyncio.wait_for` timeouts re-derived from the same formula so
      the fix doesn't just relocate the cancellation one layer up
      (`NEW-165`). **Two more layers surfaced and fixed in the same
      session, not in the original scope:** `NEW-167` — the formula's
      own rate constants (`PLANNER_MIN_PREFILL_TPS=20`/
      `PLANNER_MIN_GEN_TPS=4`) were not actually conservative; real
      measured cold-cache, thinking-mode rates on this device came in at
      roughly half both (10.63 t/s prefill, 2.15-2.74 t/s generation) —
      recalibrated to 10/2 from the real measurement. `NEW-169` — a
      third, more serious gap found while sanity-checking `NEW-167`:
      `core/planner_service.py:_request_daemon_plan()` had its own
      hardcoded client-side socket `timeout=185`, untouched by any of
      the above, shorter than every server-side timeout in the chain,
      and the real live caller's (`main.py`'s interactive planning-
      oracle RPC) own effective timeout — meaning the whole three-round
      formula rebuild was moot for its one real production caller until
      this layer was also derived from the same formula. A final review
      pass traced `core/planner_client.py`, `main.py`, and
      `core/daemon.py`'s connection-accept loop and confirmed no fourth
      layer exists. **Live-verified:** two different real thinking-mode
      planning prompts on this device returned non-empty, usable plans
      (`finish_reason: "stop"`, 167 and 203 completion tokens, both well
      under the 2048-token budget) via the real `core.plannd.get_plan()`
      production path — this closes `NEW-164` for the cases tested; it
      does **not** prove a prompt that drives the reasoning trace to the
      full 2048-token budget would still succeed (untested this round,
      stated honestly as such). Two minor findings logged and left open:
      `NEW-170` (the broken-import fallback timeout is itself a flat
      1400.0s constant, safe only up to ~3060 estimated prompt tokens)
      and `NEW-171` (one new test re-derives the timeout formula inline
      instead of calling the real implementation — test-quality gap, not
      a production defect). `NEW-168` (a separate false-positive bug in
      the "plan may be truncated" diagnostic, found during M1-E's own
      verification pass) was not addressed here and remains open. Tests:
      658 passed, 1 skipped (`tests/`), 68 passed (`ccos/tests/`). See
      `PROJECT_LOG.md`'s 2026-08-23 M1-E-fix entry for the full
      three-round discovery narrative.
- [x] **M1-G** — re-check prompts against the new model: re-run
      `system_prompt.py`'s existing A/B fixtures before editing it;
      revisit `PLANNER_PROMPT`'s size and worked examples (`NEW-50`) once
      thinking mode works; verify `--jinja`'s formatting change to the
      coding path. **Measure first, edit second.** **2026-08-25: scoped
      into a pre-registered test plan (desk-only this round, no model
      loaded, no prompt text edited) — see `PROJECT_LOG.md`'s 2026-08-25
      M1-G scoping entry for the full G1-G4 breakdown.** Desk findings:
      `prompts/system_prompt.py` at HEAD is byte-identical to
      `.live_verify_scratch/system_prompt.FIXED.py` — the `NEW-30`
      read-before-patch fix is confirmed committed, so its existing A/B
      fixture (`.live_verify_scratch/fixture_b_small.py`, confirmed
      resolving inside `WORKSPACE_ROOT`) is directly reusable without
      reconstruction. `core/plannd.py`'s `PLANNER_PROMPT` at HEAD
      (`edc9e36`) still contains the fibonacci worked example `NEW-50`
      traced as its leak source (lines ~137-149) — the leak source was
      never removed, so `NEW-50`'s "does it still reproduce on
      Qwen3.5-4B thinking mode" is a live open question, not a stale one.
      Item 3 (`--jinja`'s formatting change to the coding path) is
      **already partly closed by M1-E** — a real jinja2 render plus a
      real coding-path request confirmed no vision-namespace leakage
      (`NEW-160`, closed) — the remaining residual (does the jinja-
      rendered template preserve `system_prompt.py`'s tool-calling
      instructions intact for the read-before-patch case specifically) is
      folded into G2 below rather than tested separately. **2026-08-25,
      G2/G3 live cycles run — M1-G still NOT done.** G1 done (prior
      entry). **G2 split**: grounding 3/3 clean (no hallucinated
      `old_str`), but the read-before-patch sequencing criterion turned
      out unmeasurable with this prompt shape — `core/context.py`'s
      auto-preload loads any named file into context before inference,
      so draws 1-2 never needed to call `read_file` (`NEW-182`). Item 1
      and item 3's residual do **not** close; the first-proposed **G2b**
      (re-run `ab_driver.py`'s daemon-step-shaped `case1_prompt`, which
      the original 2026-07-31 pass used without triggering the preload)
      was checked and found **not viable** — that old run escaped the
      preload only because of `NEW-62`, a same-day regex fix for
      `detect_filenames()`'s leading-dot handling; the post-fix regex at
      HEAD resolves the same path and preloads it too (confirmed by a
      direct call today). A viable G2b needs a different design — not yet
      designed, see §4.2's M1-G entry and `NEW-182` for the full trace.
      `NEW-182` also directly confirmed the *original* `NEW-30` fix's
      0/3-vs-3/3 A/B result is not retroactively confounded by this
      mechanism, so no rule-6 downgrade applies there. **G3 clean 5/5** on both `content`
      and `reasoning_content`, non-circularity confirmed via `git log -L`
      against `d674a0c` predating `NEW-50`'s filing — real evidence the
      leak doesn't reproduce on Qwen3.5-4B in this sample, but per rule 5
      this is "not reproduced," not "fixed," and a new finding
      (`NEW-183`) notes this exact test prompt's answer is now embedded
      verbatim twice in `PLANNER_PROMPT`, weakening it as a future
      discriminator. **G4 not needed** (no leak reproduced). **Status:
      G1 done, G2 needs redo via a redesigned G2b (not yet designed — the
      original proposal was checked and rejected as not viable, see
      `NEW-182`), G3 closed, G4 not needed — M1-G as a whole remains
      open.** **2026-08-25 (second round, desk-only): a viable G2b design
      now exists and is pre-registered — see §4.2's M1-G entry for the
      full spec (exact fixture, exact prompt, N=3, precondition gate,
      grading rules). It uses a `.cfg` fixture (`.live_verify_scratch/
      case_g2b_anchor.cfg`) because `detect_filenames()` full-matches any
      real `.py` filename in any phrasing, leaving a non-matching
      extension as the only deterministic escape; empirically confirmed
      `detect_filenames()`/`auto_load_from_prompt()` return `[]` for the
      exact prompt. Found and logged a new bug in the process
      (`NEW-185`): the regex silently truncates `.cfg`/`.pyi`/`.pyx`/
      `.tsx`/`.jsx`/`.hpp` to a shorter listed extension instead of
      failing to match, which is why the escape works but also why the
      precondition gate (not just this design's reasoning) must be
      re-run every time this test is drawn. **2026-08-25, third round:
      G2b run live — grounding 3/3, sequencing 3/3, clean.** Precondition
      gate 5/5 passed fresh; RAM discipline followed (`free -h` 4.9Gi→
      5.4Gi available, PIDs 23098→31624 across a thermal-restart mid-run,
      confirmed unloaded after). All 3 draws read the fixture before
      patching it, with a grounded `old_str` every time; content-trap
      corroboration (a deliberately unspaced value a guess would likely
      get wrong) never fired since no draw guessed, so the result rests
      on trace order plus the precondition gate's payload-absence check,
      not a caught bad guess — real but narrower evidence than the design
      hoped for. A scorer regex bug initially misread all 3 draws as FAIL;
      caught and corrected in-session against the same captured output,
      no new inference spent (see `NEW-182`'s third update and
      `NEW-186`, a new duplicate-`note_save` finding from this run, for
      full detail). **M1-G status, final: DONE.** G1 done, G2's grounding
      3/3 (the live axis in the `.py`-preload domain) + G2b's 3/3-and-3/3
      (the live axes in a genuine no-preload domain) together give item 1
      and item 3's residual a real, narrow positive measurement; G3 closed
      5/5 with the rule-5 caveat; G4 not needed. The one residual — `.py`/
      `.json`-domain sequencing specifically — has no reachable test
      design at HEAD without fixing `core/context.py` (out of scope) or an
      explicit preload bypass (not built), so it stays open as `NEW-182`
      (a standing methodology-gap finding) rather than blocking this item.
      No prompt edit was made or is warranted by this round's
      measurements — see §4.2's M1-G entry for the full writeup.
- [x] **M1-F** — re-derive `MAX_CONCURRENT_MODEL_BUDGET_BYTES` and
      `MAX_SWAP_ASSIST_BYTES` from M1-E's measurements (`NEW-156`) —
      **DONE 2026-08-24, code-complete, code-reviewer-approved
      2026-08-25, not live-verified** (no live component by design).
      8.90GiB → 7.00GiB;
      10.00GiB → 6.50GiB. See §4.2's M1-F entry for the full derivation,
      the `NEW-179` invariant fix (budget ceiling must stay ≥ the device
      ceiling — undocumented and untested before this round, caught by
      the existing test suite), and `NEW-180` (embed RSS still
      unmeasured).

Then:

- [ ] **7.4** — resource gate + slot-aware loader. 5/5 sub-tasks
      code-complete and code-reviewer-approved (2026-08-09). Core
      admission→load→CLI-recovery path live-verified (round 18). Left:
      a production-config live pass — now re-targeted at Qwen3.5-4B and
      covered by M1-E. The old 7B-at-32768 script is obsolete.
- [x] **7.4a** — swap-aware budget check. A/B/C1/C2/D/F built and
      approved; E and G run. `NEW-135`/`NEW-136` **FIXED 2026-08-25, code-
      reviewer-APPROVED 2026-08-25** (later same day — mandatory rule-4
      pass on commits `3513661`/`f7511bb`: lock coverage confirmed
      complete, no RAM/swap double-counting, no leak on slot release, the
      `..._wiring_actually_uses_persisted_pending_claim` regression test
      independently re-verified by hand-reverting the fix, full suite
      independently rerun at 669 passed/1 skipped matching the
      implementer's count). Not live-verified (no live component by
      design — admission-accounting logic). `core/resource_gate.py`:
      `reserved_swap_bytes` param on
      `compute_swap_assisted_headroom_bytes()`/`can_admit()`,
      `GateDecision.swap_bytes_claimed`, `reserve_slot()`'s PENDING-swap
      sum, `total_reserved_swap_bytes()`. Fixes the `reserve_slot()`/
      `can_admit()` path only; `can_dispatch_task()`'s separate consumer
      stays an open, documented gap (no slot to attribute its claim to) —
      reviewer judged it acceptable-but-real and it is now tracked as
      **`NEW-187`** (open), not just prose. `NEW-140` scenario 3 and
      `NEW-141` **CLOSED 2026-08-25**, each on its
      own correct evidence (not the same evidence for both — scenario 3 is
      single-model, not concurrent): `NEW-141` on `core/planner_loader.py`/
      `_evict_planner_and_confirm_free()`'s confirmed absence from HEAD;
      `NEW-140` scenario 3 on M1-B's confirmed repoint of every model-role
      path onto Qwen3.5-4B (the retired 7B's specific figures no longer
      describe any live path). `NEW-140`'s other, model-independent content
      stays open. **7.4a stays unchecked**: `NEW-187` and `NEW-140`'s
      remaining open content are both standing items outside this round's
      closure, not oversights.
      **Status update, 2026-08-26** — `NEW-187` FIXED (`can_dispatch_task()`
      now reads `total_reserved_swap_bytes()`, one-directional by design
      since dispatch registers no slot and has no durable claim of its own),
      2 new tests, full suite 671 passed/1 skipped — **code-complete, still
      needs its mandatory rule-4 code-reviewer pass** (none available this
      session). `NEW-140`'s remaining content re-measured against real
      Qwen3.5-4B cost and current `MAX_SWAP_ASSIST_BYTES` (6.50GiB): the
      exact historical `NEW-21` fixture now admits at ALL FOUR
      `MemAvailable` points in its plausible range, worse than the stale
      retired-7B figures' 3-of-4 — see new **`NEW-188`**. Stays open,
      severity upgraded, not closed.
      **Status update, 2026-08-26 (confirmatory pass)** — `NEW-187`'s
      first review pass returned CHANGES REQUESTED: the read-failure
      fallback failed permissive (`reserved_swap_for_dispatch = 0`)
      instead of disabling the swap branch, inconsistent with the
      sibling `CODEY_SWAP_ASSIST_ADMISSION` handler's fail-closed
      pattern in the same function, and with `NEW-188`'s same-round
      finding making the wrong direction especially costly to accept.
      Fixed same round (`swap_assist_enabled = False` on read failure,
      test renamed/flipped, docstring's "never writes" claim corrected
      for `list_slots(reap_dead=True)`'s real mutation) —
      confirmatory re-review **APPROVED**, 671 passed/1 skipped
      independently reproduced. `NEW-187`'s own review chain is closed.
      **7.4a's checkbox stays unchecked**: solely blocked now on the
      still-never-run live low-swap-headroom single-model verification
      pass `NEW-140`/`NEW-188` call for.
      **Status update, 2026-08-26 (live-verification pass) — that pass
      HAS now been run, natural-state-only per Ish's explicit scope
      choice for this round (no deliberately-induced memory pressure).
      Result is genuinely mixed, not a clean close.** Real production
      `python3 main.py --no-resume` call (M1-E's established path), one
      load/unload cycle: `free -h` `4.2Gi used, 806Mi free, 6.3Gi
      available` → `3.2Gi used, 5.2Gi free, 7.3Gi available`; `ps aux |
      grep llama-server` clean before/after; graceful `/exit` teardown,
      no residual PID. Real `/proc/meminfo` at the moment `reserve_slot()`
      ran: `MemAvailable=6.0321GiB`, `SwapFree=14.415GiB` of 16.000GiB
      (90.1% free). Real `GateDecision`: `admitted=True admitted_via_
      swap=True swap_bytes_claimed=35,048,904` bytes,
      `estimated_cost_bytes=5,209,547,936` — the last figure matches
      `NEW-188`'s desk-derived cost exactly, a real-production
      confirmation of that entry's arithmetic input. **Axis (a) — does
      swap-assist activate live on the real device under real ambient
      conditions: CONFIRMED, first time**, closing that specific
      sub-question. **Axis (b) — the compound low-RAM-AND-low-swap
      `NEW-21`-shaped distress state `NEW-140`/`NEW-188` are actually
      about: NOT reproduced.** `SwapFree` was 90.1% free, nowhere near
      `NEW-21`'s `SwapFree≈6.8GiB`-of-8GiB fixture; the operand that
      bound was `MAX_SWAP_ASSIST_BYTES`'s cap headroom, not swap
      scarcity. Third consecutive live session (after the two `NEW-137`/
      sub-task E sessions) finding this device's swap pool healthy during
      a real model load. **7.4a's checkbox stays UNCHECKED, but the
      residual is now narrower and precisely stated: general swap-assist
      activation is confirmed live; only the compound low-RAM+low-swap
      state remains unobserved.** Whether that residual needs a future
      deliberately-induced pass or can be accepted as a standing
      documented risk is Ish's call, not resolved here — logged as §8
      Q10. Full numbers and both-axis framing in `NEW-140`'s and
      `NEW-188`'s own 2026-08-26 updates. No code was touched this round
      (docs reconciliation only); §6.2's Phase A1 ordering (the lease/
      registry, the concurrency test) is unaffected — nothing downstream
      assumed 7.4a would close on this pass, so no pointer changes.
      **Status update, 2026-08-26 (Ish's decision on §8 Q10) — 7.4a is
      now CLOSED.** Ish's exact words: "accept the residual as a standing
      documented risk for now." **Precise scope of "closed," stated
      honestly rather than left to imply more than it means:** (1) the
      narrower question — does swap-assist genuinely activate on the
      real device under real ambient conditions — is CONFIRMED LIVE (the
      immediately-preceding status update's `admitted_via_swap=True`
      pass); (2) the compound low-RAM-AND-low-swap `NEW-21`-shaped
      distress scenario `NEW-140`/`NEW-188` are actually about was NEVER
      OBSERVED LIVE across three consecutive real-device sessions, and is
      now closed by Ish's explicit risk-acceptance decision, not by a fix
      or a successful reproduction. **This is a risk-acceptance closure,
      not a "verified safe" claim** (rules 5/6): the underlying
      arithmetic — the exact `NEW-21` fixture admits at all four
      plausible `MemAvailable` points under the current 6.50GiB
      `MAX_SWAP_ASSIST_BYTES` cap — remains true and undisputed; the
      decision is to stop pursuing a live reproduction on this device,
      not to declare the mechanism harmless. See §8 Q10 for Ish's exact
      wording and `NEW-140`/`NEW-188`'s own 2026-08-26 status lines for
      how each finding is marked following this decision.
- [ ] **7.4b** — model lifecycle policy, reshaped by §1.4. **A is now
      fully closed; C's live-verification gap (both interactive AND
      background halves) is now closed too, but C as a whole — and
      therefore the 7.4b parent checkbox — stays unchecked pending
      `NEW-145`/`NEW-149`/`NEW-155`'s underlying race conditions and the
      background ceiling's own re-derivation from §5.1 (see C below).**
  - [x] **A** — embed model always resident from Codey startup to
        shutdown. Implementation landed via `5687dcf`; **code-reviewer
        pass done 2026-08-23** as part of the M1-B/C/D combined review
        (§4.4) — APPROVED. **LIVE-VERIFIED 2026-08-26** under a real
        `codey-start` full-stack launch: embed `llama-server` (PID
        31070) came up immediately at daemon startup, before any coder
        request, and the same PID survived unchanged through the
        coder's load, a 12-minute interactive stall (`NEW-195`), and a
        severe RSS-eviction event (`NEW-180`'s third sample) — the
        96-line `~/.codeyOS/codeyOS.log` (spans `Daemon PID: 31066`
        through `Daemon stopped`; copy preserved at
        `docs/archive/live-evidence/2026-08-26-7.4b-codey-start/`)
        shows no restart line for it anywhere in that span. **Fully
        closed: code-complete, code-reviewer-approved, live-verified.**
        Blocking prerequisite
        `NEW-144` was the kill-and-replace-a-healthy-occupant bug.
        Unaffected by §1.4 — the embedding model is not being replaced.
  - [x] **B** — planner context ceiling 8192. **Implemented** as
        `get_planner_n_ctx()` in `utils/config.py` (landed in `5687dcf`,
        never separately reviewed) — this plan's 2026-08-21 claim that it
        was "not started" was wrong, corrected per rule 6. **Moot under
        §1.4**: no separate planner survives. M1-B retires the function.
  - [x] **C** — coder interactive-vs-daemon context branching. Landed +
        `NEW-152` fix (`6528446`); **code-reviewer pass done 2026-08-23**
        as part of the M1-B/C/D combined review (§4.4) — APPROVED.
        **Checkbox is `[x]` for the built/reviewed work only — live
        verification is incomplete; do not read this box as "fully
        live-verified" (the `NEW-181` mismatch shape this project has
        already been bitten by once).** 2026-08-26 real `codey-start`
        pass: the **interactive half is live-verified** — on-disk
        evidence is `~/.codeyOS/llama-server.log:1`'s spawn command line
        carrying `-c 65536` verbatim (copy preserved at
        `docs/archive/live-evidence/2026-08-26-7.4b-codey-start/`),
        corroborated by `ps` at spawn time; genuine cold spawn against a
        clean pre-launch baseline (no reuse-branch confound).
        (Live-verifier's session also reported a console line `Coder
        n_ctx=65536 (interactive session active)` not present in the
        persisted `codeyOS.log` — cited as reported, not as an
        independently-checkable artifact.) **Status update, 2026-08-26
        (second live pass, clean(er) re-run): the background/
        daemon-dispatch half is now ALSO live-verified, first time
        ever.** With the daemon running alone (no TUI attached,
        `is_interactive_session_active()` confirmed `False`), a task
        submitted directly via `core/state.py`'s real
        `StateStore.add_task()` (the same DB the daemon polls, not a
        synthetic call) was picked up and spawned `llama-server ... -c
        16384 -t 6 ...`, matching `get_coder_background_n_ctx()`
        (`utils/config.py:137`) exactly. Task completed normally
        (`status: done`, `result: 'Done.'`), wall time 319s. **This
        closes the live-verification GAP this checkbox was flagging —
        both context branches now have real spawn-command-line
        evidence — but it does not close item C itself**, for two
        reasons that this round's spawn ordering did not exercise:
        (1) `NEW-145`/`NEW-149`/`NEW-155` describe specific interleaved
        orderings (the daemon's eager path winning a race against a
        later-attaching TUI, or whichever caller spawns first winning
        the context size for a shared server's whole life) — this
        round's interactive session loaded cold and alone first, and the
        background test ran afterward against a freshly-restarted
        daemon, so neither race was actually put under test; both stay
        open. (2) The background ceiling (16384) is still the same
        "known-safe intermediate point" `utils/config.py`'s own comment
        at `get_coder_background_n_ctx()` cites from TODO.md 7.4a
        sub-task E — it has not itself been re-derived from §5.1's real
        Qwen3.5-4B cost figures the way the interactive ceiling (65536)
        was via Ish's explicit 2026-08-22 direction (§5.1). That
        re-derivation is still outstanding.
      - **`NEW-195`'s hang, re-tested same round: did NOT recur, but
        this is NOT read as "confound proven, defect ruled out."** The
        same trivial "ping" prompt this time completed in 324.8s (before
        correctly stopping to ask for shell-command confirmation) rather
        than stalling past 700s. This re-test changed two variables at
        once relative to the original capture, not one: the confound was
        substantially (not perfectly — a brief ~3s foreground blip
        coincided with the prompt send) reduced, AND `NEW-197` had
        separately raised `n_threads` 4→6 in between, which `NEW-197`'s
        own measured numbers show could plausibly explain a comparable
        speedup on its own. See `NEW-195`'s own entry for the full
        reasoning; the honest conclusion is that 700+s of non-completion
        is no longer this scenario's only known data point, and nothing
        in either session currently requires an internal defect — but a
        single-variable, fully isolated re-run has still never been run.
        `NEW-145`, `NEW-149`, `NEW-155` remain the concrete, open,
        code-level gaps blocking this item regardless of how `NEW-195`
        eventually resolves. The
        policy survives §1.4; the background ceiling still needs
        re-deriving from §5.1 (the interactive ceiling, 65536, already
        was, per §5.1/Ish's 2026-08-22 direction).
  - [x] **D** — folded into M1-F, **DONE 2026-08-24**: re-derived
        `MAX_CONCURRENT_MODEL_BUDGET_BYTES` (§ M1-F entry above) now
        reflects there being no separate planner process, executed with
        real numbers instead of left unchanged by inertia.
- [ ] **Lease/registry** — replace port-probe adoption with an explicit
      lease. Absorbs `NEW-104`, `NEW-144`/`NEW-146`, `NEW-149`.
      Prerequisite for a shared model server; more load-bearing under
      §1.4, since one server now has more consumers.
      **Status, 2026-08-26: code-complete, self-tested (692 passed/1
      skipped), NOT yet mandatory-code-reviewer-approved (rule 4 — this
      is lock/process-coordination code; no code-reviewer subagent
      available in the implementing session).** Built as a registry query
      against the existing resource-gate slot store (`find_resident_slot()`)
      plus a positive-PID-resolution toolkit generalized from
      `embed_server.py`'s own pattern (`resolve_port_owner_pid()`,
      `_pid_owning_inode()`, `pid_cmdline_contains()`,
      `resolve_spawned_n_ctx()`) — never a name-based kill, per rule 3.
      `core/loader_v2.py`'s coder-adoption path and `core/embed_server.py`'s
      `start()` (fixing `NEW-146` at the daemon's own restart path, not
      just `NEW-144`'s `inference.py` caller) both now register/detect
      adopted servers instead of leaving the gate blind to them; a
      slot-release leak the adoption fix would otherwise have introduced
      into `stop()` was caught and fixed in the same round. **Real,
      confirmed platform limitation (`NEW-200`, not a code defect)**:
      `/proc/net/tcp`/`tcp6` are `PermissionError` on this actual device
      for every caller — `resolve_port_owner_pid()`'s primary path cannot
      resolve a truly-foreign (no pre-existing slot) process here, so
      `NEW-104`'s hardest case stays only partially closed on this
      specific device; the two cases that don't depend on this OS call
      (a self-registered slot; `embed_server.py`'s existing
      registered-slot fallback) work correctly. See §4's summary-table
      row for the full writeup and `NEW_ISSUES.md`'s `NEW-104`/`NEW-144`/
      `NEW-146`/`NEW-149`/`NEW-200` entries. **Mandatory code-reviewer
      pass still outstanding — do not mark this checkbox done until it
      runs and approves.**
- [ ] **Concurrency test** — can one `llama-server` serve the daemon, the
      TUI/GUI, and both limbs via slot/`--parallel`? No flag set anywhere
      today. **Now the central question of this phase.**

### Phase A2 — coding-domain rollout (§6.8)

- [ ] **7.3 sub-task E** — dispatch on the tier decision (A–D built,
      log-only). Must address `NEW-126` and the missing remote-tier path.
      **Re-scoped 2026-08-24 (`NEW-172`, `NEW-126` further corrected):**
      A–D's `classify_tier()`/log-only integration lives inside
      `core.planner_service.get_plan()`, which has **zero production
      callers** — `main.py` calls `_request_daemon_plan()` directly,
      `core/agent.py` uses a different `core.planner.get_plan()`, the
      daemon's `plan_only` RPC calls `core.plannd.get_plan()` directly,
      and `core/task_executor.py` bypasses planning entirely
      (`no_plan=True`). Sub-task C's block has therefore never executed
      outside its own test file, and no log evidence exists to tune
      thresholds against. Separately, the easy-tier skip this sub-task
      was headed toward is **already shipped** at both live entry points
      — `main.py:492`'s `if not is_complex(prompt): return
      run_agent(...)` (before `_try_daemon_plan()`) and
      `core/agent.py:1271`'s `if is_complex(user_message) and
      not _in_subtask and not no_plan:` — both using
      `core.orchestrator.is_complex()`/`_score_message()` already. What
      remains under this sub-task: (a) the medium/hard split via
      `enable_thinking` on `plannd.get_plan()` (unaffected by this
      finding, still the planned next task), and (b) a consolidate-or-
      delete decision on the orphaned `planner_service.get_plan()` and
      dead `model_tiers.classify_tier()`, which overlaps 4.3's "migrate
      both call paths onto one boundary" below — a design call for Ish,
      not an implementer task.
      **Reconciled 2026-08-24 (Ish approved building all three tiers in
      one push):** two scoping passes (easy vs. medium/hard) ran in
      parallel and disagreed on where the decision point lives — reconciled
      into two sequenced, implementer-ready tasks. **Task A (delete):**
      remove `planner_service.get_plan()` and `model_tiers.classify_tier()`
      (loses its only caller; already degenerate/constant-valued post-M1-D
      — see `tests/test_model_tiers.py`'s `TestClassifyTier` docstring),
      plus `tests/test_planner_service_classify_tier.py` and the
      `TestClassifyTier`/`TestClassifyTierFullChainIntegration` classes in
      `tests/test_model_tiers.py`. Keep `MODEL_TIERS`/`ModelTierEntry`/
      `get_tier()`/`tiers_for_role()` — a legitimate, independently-tested
      data table with no other production consumer, not itself dead.
      **Task B (build):** the real decision point is
      `main.py:490-495` (`score = _score_message(prompt)` computed once,
      passed to both `is_complex(prompt, score=score)` — new optional
      param — and threaded through `_try_daemon_plan(prompt, no_plan,
      tier)` → `_request_daemon_plan(prompt, tier)`, which is NOT being
      deleted). Tier split on the post-easy-gate population: `tier =
      "medium" if score.length > 300 else "hard"` (reuses `is_complex()`'s
      own existing `length > 300` boundary — see `NEW-174`'s note that
      this boundary is currently dead-identical to `length > 150` in
      `is_complex()` itself, unrelated defect, not blocking) — `hard`
      is the default/fallback matching M1-D's thinking-mode-by-default
      design; log the chosen tier plus `has_action`/`length`/
      `signal_count` on every decision so the boundary is tunable from
      real traffic later. Fenced out of Task B: `core/agent.py:1271`'s
      `plan_tasks()` fallback and `core/planner.py:get_plan()`'s
      `--plan`-flag path (`NEW-175` — different mechanisms, no
      `chat_template_kwargs` hook) and `NEW-168`'s truncation-heuristic
      fix (`NEW-173` — touches both plannd backends, not a cheap fold-in
      as originally proposed). Full brief with exact signatures, the
      GGUF-verified `enable_thinking:false` behavior, the
      `functools.partial`/`run_in_executor` mislabeling trap, and the
      timeout-nesting invariant (`PLANNER_MAX_TOKENS_MEDIUM <
      PLANNER_MAX_TOKENS`, must be commented at the constant) is in the
      2026-08-24 project-architect reconciliation.
      **Task A: DONE, 2026-08-24, code-reviewer-approved** —
      `planner_service.get_plan()`/`model_tiers.classify_tier()` and
      their dedicated test file/classes actually deleted (not just
      scoped); `MODEL_TIERS`/`get_tier()`/`tiers_for_role()` confirmed
      untouched. Test count: 658→644 passed (14 removed, matching
      exactly what was deleted), 1 skipped, `ccos/tests/` unaffected at
      68 passed — see `PROJECT_LOG.md`'s 2026-08-24 Task A entry for the
      full arithmetic and the pre-existing `main.py`-git-clean test
      fragility (`NEW-177`) found and correctly isolated as unrelated
      during review.
      **Task B: DONE, 2026-08-24, code-reviewer-approved.** Threaded
      `enable_thinking`/`tier` end-to-end: `utils/config.py` gained
      `PLANNER_MAX_TOKENS_MEDIUM=1024` (justified from `PLANNER_PROMPT`'s
      answer shape, not the retired 1.5B's old budget, per rule 12);
      `core.orchestrator.is_complex()` gained an optional `score=`
      param so `main.py` scores a prompt once and reuses it for both the
      easy-gate check and the tier split; `main.py` derives
      `tier = "medium" if score.length > 300 else "hard"` and logs the
      decision (guarded against firing on `--no-plan`); `core.planner_
      service._request_daemon_plan()` threads `tier` into the socket
      payload but keeps its own client-side timeout pinned to hard-tier
      sizing **unconditionally** — the critical invariant, verified in
      both directions by code-reviewer: the daemon's *own* internal
      `compute_planner_timeout()` calls DO shrink for medium tier, the
      client's outermost socket timeout never does, so an old daemon
      binary that ignores `tier` and always runs hard-tier server-side
      can never outlive a client that shrank its own wait. `core.
      planner_client.send_plan_request_async()`'s `run_in_executor` call
      was switched to `functools.partial` — without this, adding
      `enable_thinking` to `plannd.get_plan()` would have silently
      defaulted every request to hard-tier behavior via positional-arg
      forwarding, with zero exceptions anywhere; caught before it shipped.
      15 new tests (`tests/test_plannd_tier_split.py`), all independently
      re-run by code-reviewer with real discriminating assertions (exact
      equality on the tier-invariant socket timeout, exact inequality on
      the daemon's own tier-scaled timeout), not just "some value
      computed." Full suite: 659 passed/1 skipped (644 baseline + 15
      new), `ccos/tests/` unaffected at 68 passed.
      **One honest gap, logged as `NEW-178`, not silently smoothed over:**
      the daemon's dormant pull-side planning path (`_plan_claimed_task`,
      reached only via the `plan_only=False`/`needs_planning=1` path
      `NEW-112` already found has zero production callers) has no tasks-
      table column to carry a `tier` value through, so it can only ever
      plan at the `tier="hard"` default. Bounded and non-blocking since
      that path isn't reachable in production today; whoever activates it
      should add the schema column at the same time.
      **Reviewer's own note, not a defect:** `score.length` is a
      character count, so the `length > 300` boundary likely routes most
      real coding prompts to medium (non-thinking) tier — a bigger
      behavioral shift in practice than "additive, backward-compatible"
      first suggests. This is the exact boundary Ish pre-approved in the
      2026-08-24 reconciliation, not a silent implementer choice — stated
      here so it's visible rather than only findable by re-deriving it
      from the character-vs-token distinction.
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

- [x] **B1** — Core schema + canonical IDs (code-complete, 11 tests passing in `tests/test_restoricon_core/`).
- [x] **B1** — the HTTP API boundary (code-complete; rule-4 adversarial review pending for binding & auth).
- [x] **B1** — auth, roles, permissions (code-complete; 7 roles, PBKDF2 hashing, bearer tokens, customer isolation).
- [x] **B1** — Communication History + Audit Log (day-one-or-never, code-complete; append-only verified).
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
- [ ] **U.10** — **open question, §8 Q9** — investigation done, decision
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
`NEW-155`, `NEW-187`, `NEW-188`.

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
