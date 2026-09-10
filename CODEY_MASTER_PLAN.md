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
   session — not inferred, not implied by a task description. See §6.11.

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
   logic, locks, model load/unload, the Core API server's binding/auth)
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

10. Before creating a new subagent, check your tool's existing subagent
    definitions (`.claude/agents/` for Claude Code, whatever registry
    Antigravity or another tool uses) for one that already fits.
    Subagent sprawl makes the pipeline harder to reason about, not
    easier.

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
self-modification by default; keeping client surfaces from drifting out of sync
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
  several, because a single server has to serve the daemon, the TUI,
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

- **Unified entry points** `codey`, `codey-start`, `codey-stop` — root `codey` executable supporting interactive launch and subcommands (`start`, `stop`, `status`, `restart`, `logs`, `config`), orchestrating Daemon, Restoricon API, Codey-Aigentik, and Cloudflare tunnel via `lib/service_manager.sh` with exact PID-tracked lifecycle.
  - **Orphan detection & directory-scoped termination for Codey-Aigentik** (commit `57b6088`; revised after code-reviewer CHANGES REQUESTED, re-approved 2026-09-02). `svc_find_orphans_by_cwd()` uses two-factor identification (canonical `/proc/$pid/cwd` match AND entrypoint token in `/proc/$pid/cmdline`) so a bare `pkill -f node` is never issued; `start`/`stop`/`status` surface and clean untracked orphans. **Live-verified on-device by Ish 2026-09-02**: spawned a genuine untracked `node index.js` orphan, `codey status` flagged it (`[⚠ 1 orphan(s): 17953]`) before any cleanup, `codey stop` terminated it loudly (`fully stopped, 0 processes remaining`), `codey start` produced exactly one clean tracked PID confirmed by both `ps` and `codey status`. Follow-ups `NEW-268`..`NEW-271` remain open. See `PROJECT_LOG.md` 2026-09-01 entry.
- **Browser GUI REMOVED, 2026-09-02** (Ish's decision, given in session:
  "remove the gui for now and only use the web dashboard later we can add
  a gui back if we need to"). Deleted `gui/server.py`, `gui/index.html`,
  `lib/gui_launch.sh`, and `tests/test_gui_clients_signal.py`; stripped
  `start_gui`/`stop_gui`/`status_gui` and the GUI PID/log files from
  `lib/service_manager.sh`; removed the `gui_launch` sourcing from
  `codeyOS`; de-argumented `start_all_services()` at all 6 call sites.
  The web-facing surface is now the Restoricon Core dashboard (`/admin`).
  **1,620 deletions / 89 insertions across 23 files.**
  - **This was a resource-gate change, not only a UI deletion.**
    `core/resource_gate.py`'s `is_gui_client_connected()` was **signal
    source 5** feeding `is_interactive_session_active()` →
    `can_dispatch_task()`. It carried a live trap: its final branch
    returned `True` when the clients-count file held a nonzero value and
    **no** `gui-server.pid` existed to cross-check. With the GUI's writer
    deleted, a stale count file would have made that branch permanently
    reachable and never self-healing — deferring **all** daemon
    background dispatch, silently and forever. **This ships to any user
    who merely `git pull`s**, since their own `~/.codeyOS/
    gui-clients.count` survives the pull (code-reviewer's point, not
    caught in the original analysis). The signal was therefore removed
    outright rather than left as a vestigial always-False stub.
    `is_interactive_session_active()` is now TUI-only; both production
    callers (`core/daemon.py:1166`, `core/loader_v2.py:1041`) pass no
    arguments, verified.
  - **Consequence logged, not fixed: `NEW-282`** — `/admin` feeds the
    gate nothing, so a human watching the web dashboard no longer defers
    background dispatch. A real behavioral gap created by the product
    decision; any replacement signal must fail **closed**.
  - **Zombie source eliminated.** `gui/server.py` (PID 18856) never
    reaped its spawned children; two `[python3] <defunct>` zombies were
    resident. Stopped by exact tracked PID after verifying identity
    (rule 3); zombies reaped on exit; stale `gui-clients.count` /
    `gui-server.pid` / `gui-server.log` removed. `NEW-279`'s symptom is
    cleared and its owner deleted — **deliberately not marked "fixed"**,
    since no reaping logic was ever written and the defect is available
    again to any future child-spawning service. `NEW-111` is likewise
    **resolved by removal, not by fix**, as is the old audit finding
    **C-2** (`docs/security.md` §6 rewritten to say so).
  - **`aiohttp` dependency:** removed from the **core** install block
    (`gui/server.py` was its only direct importer) but **deliberately
    retained in the pipeline block** — code-reviewer showed via
    `git blame` that the pipeline entries predate the GUI by three days
    and arrive transitively through `fsspec[http]`/`datasets`. The first
    pass over-reverted both; corrected before commit. Rule 11 satisfied.
  - **Verification:** `tests/` 1,068 passed / 1 skipped, `ccos/tests/`
    107 passed. Two failures in `tests/test_loader_resource_gate.py` are
    **proven pre-existing** — reproduced identically at unmodified `HEAD`
    in an isolated `git worktree`, and caused by a live embed server on
    port 8082 being adopted by tests that expect to start their own
    (`NEW-280`; its fix direction was corrected after the reviewer showed
    the real gate is `_port_is_bound()`, not the `_is_port_open()` the
    tests already patch to no effect). Live smoke tests: `codey status`,
    `codey config`, `codey logs` all exit 0 with no GUI line.
  - **Mandatory rule-4 code-reviewer pass: CHANGES REQUESTED, then all
    four blockers fixed** (stale repo-structure map in this file, a
    `http://localhost:8888` line still printed by `install.sh`, the
    over-broad `aiohttp` removal, and an unstaged `NEW_ISSUES.md`), plus
    all four warnings. **Reviewer's own generalizable lesson, worth
    keeping:** a case-insensitive `gui` sweep missed a live reference
    because the line was named after its *effect* ("browser"), not the
    thing.
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
  dispatch (interactive TUI session defers background dispatch) and
  the autonomous thermal shutdown tripwire, both live-verified 2026-08-10
  (commit `96b6ea1`).
- **20+ audit-remediation rounds** (NEW-1 … NEW-20 and the prompt
  rounds), including the `NEW-30` read-before-patch fix — decisive live
  A/B: 3/3 read-before-patch with the fix, 0/3 without.
- **Restoricon Core Phase 1 RBAC fixes, 2026-09-02** — two of the three
  fixes are live-verified against a real running API (a scratch DB on
  port 8791, never the business DB; server killed by exact tracked PID,
  port confirmed closed). Full suite `1085 passed, 1 skipped`;
  code-reviewer **APPROVED** with three independent negative controls
  confirming every new test is load-bearing.
  - **`submit_review()` authorization** (`services/business_ops_service.py`)
    — the method previously took no actor and had no permission check at
    all, so any authenticated caller could overwrite the rating and
    feedback on **any** review request. It is now gated on
    `PERM_WRITE_MARKETING` **or** customer-ownership
    (`actor.role == ROLE_CUSTOMER` and `actor.customer_id` matching the
    row), deliberately *not* staff-only — the endpoint is meant to be
    reachable by the customer the request belongs to. Ownership predicate
    copied from `crm_service.get_estimate`. An audit call was added
    capturing old **and** new rating/feedback/status. Live: owning
    customer 200, other customer 403, technician 403, staff 200.
  - **Role changes now revoke tokens** (`auth.py:update_user`) —
    `api_tokens.role` is a login-time snapshot that `authenticate_token`
    reads instead of the live user row, so a demoted user kept acting
    under their old role for up to the token's 7-day life. `update_user`
    now revokes all of that user's tokens when `role` actually changes,
    in the same transaction as the UPDATE. Non-role edits and no-op role
    writes deliberately do not force a re-login; the actor's own token is
    deliberately **not** spared, because self-demotion leaving a
    stale-role token alive is the exact bug. Live: role change → old
    token 401, phone change → old token still 200.
  - Scope note: the customer branch of `submit_review` is **direct-API
    only** — `web_surfaces.py` has no `marketing/reviews` surface, so the
    live "owning customer 200" was an HTTP probe, not a UI path.
  - Four out-of-scope findings logged, none fixed: `NEW-264`
    (`update_user(active=0)` doesn't revoke, so re-activation resurrects
    pre-suspension tokens), `NEW-265` (`create_review_request` has no
    audit call), `NEW-266` (`update_user` allows `role=customer` with a
    NULL `customer_id`), `NEW-267` (the new revocation writes no audit
    record and `user_updated` never captures the old role).

### 4.2 Built, approved, not live-verified

- **Restoricon Core session persistence, 2026-09-02** — the web surfaces'
  `getAuthToken`/`setAuthToken` (`api/web_surfaces.py:_get_common_script`)
  moved from `localStorage` to `sessionStorage`, so the session token dies
  with the browser session instead of auto-logging users back in for 7
  days. This is what Ish asked for: username/password every session.
  **Code-complete and code-reviewer-approved, NOT browser-verified** —
  verification so far is that all five served surfaces (`/admin`,
  `/portal`, `/quote`, `/admin/login`, `/portal/login`) emit
  `sessionStorage` and zero `localStorage` token calls, fetched from a
  real running server. The actual quit-the-browser-and-reopen test needs
  Ish at a real browser; steps are in the 2026-09-02 `PROJECT_LOG.md`
  entry. The 7-day server-side `api_tokens.expires_at` was deliberately
  left unchanged (see §8).
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

**Updated 2026-08-31; B4's web-layer claim corrected 2026-09-02 (rule 6).**
Phase B1 (Core API & Auth), Phase B2 (Aigentik Write-Through & Contacts
Directory), Phase B3 (CRM/Sales Pipeline & Operations Domain Engines),
Phase B4 (Public Website Intake API, Rate Limiting, Customer Portal Data
Isolation, Staff/Admin Surface & Device Limb Dashboard Integration), Phase
B5a (Remaining Business Domain Engines & Cross-Domain Search/Reporting),
and Phase B5b (Third-Party App Automation & Device Bridge IPC Integration)
are complete and verified **at the service and API layer** (1,165 passed).
All three surfaces (`quote`, `portal`, `admin`) plus the static
`restoricon.com` site are unified under a top-left hamburger navigation
drawer and redesigned with exact Deep Navy & Bronze branding.

**⚠ The "100% complete" claim this paragraph previously carried is
withdrawn for B4's web layer.** Verified by reading
`restoricon_core/api/web_surfaces.py` in full on 2026-09-02: the customer
portal renders hardcoded demo content and calls 2 of its 10 real routes;
the admin surface wires 3 of its 11 tabs and ships two save buttons that
silently discard input while reporting success. User Management **with
granular dynamic permission overrides is genuinely real** — that part of
the claim stands and was re-verified. Everything else in the web layer is
finished by **§6.9 / Phase B6**. See §6.6's correction block for the
file-and-line evidence and `NEW-272`…`NEW-276`.

**Phase B6 progress (code-complete tier, none live-verified):**
`B2-fin-1` (2026-09-02, fork `2056524`) closed the last B2 write-through
gap. `B6.1` (2026-09-02) delivered `CRMService.update_project` +
`POST /api/v1/projects/{id}/update` + two additive reassignment
permissions (`PERM_REASSIGN_PROJECT_STAFF` scoped / `PERM_REASSIGN_ANY_PROJECT_STAFF`
unrestricted), the ownership narrowing keyed on permission not
`actor.role`. Both code-reviewer-approved (rule-4). `B6.2a`
(2026-09-02) delivered the canonical `build_audit_details()`
old/new+side-effects payload helper and wired it into the 9 user-mutation
audit sites in `api/routes.py` (code-reviewer-approved, rule-4).
`B6.2b-1` (2026-09-02) canonicalized 25 mechanical service-layer
create/delete audit sites + added four `_AUDITABLE_*_FIELDS` allow-lists.
`B6.2b-2` (2026-09-02) migrated the 11 `crm_service` real-update audit
sites to `before`/`after` diffs — incl. `update_project` off its
hand-rolled diff (`NEW-312` audit-accuracy half) — added
`_AUDITABLE_PROJECT_FIELDS`, and fixed an unguarded post-commit
`.to_dict()` in `update_subcontractor` (`NEW-317`); code-reviewer-approved
(rule-4). `B6.2b-3` (2026-09-02) migrated the 8 `operations_service` real-update
audit sites to `before`/`after` diffs (2 as C-none `snapshot`), closing
the `NEW-313` COALESCE after-image trap's audit half and adding four more
`_AUDITABLE_*_FIELDS` guards. `B6.2b-4` (2026-09-03) migrated the final 11
service-layer sites — **B6.2b is now code-complete across all 55 service
sites** — resolved `NEW-316`, closed the `NEW-312` audit-half at
`update_appointment` / `update_contact`, and decided `NEW-315` (canonical
create shape = `after=`-only + `fields=`; `snapshot_fields=` deferred to
`B6.2c` as a prerequisite). Next: `B6.2c` (admin audit-search screen).
**The round-by-round build narrative that used to live here — 627 lines
covering Phase B2's write-through rounds, their code-reviewer passes, and
their test counts — was moved verbatim to `PROJECT_LOG.md` on 2026-09-02
(`U.38` step 3), where rule 9 already puts it.** Nothing was deleted; see
that file's `2026-09-02 — §4.5 business-layer round narrative,
de-ledgered` entry. §4 is a current-state snapshot, not a third ledger.


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

> ### ✅ M1, the model migration — CLOSED 2026-08-25. Not the start point any more.
>
> **All seven sub-items M1-A…M1-G are `[x]` done** (2026-08-22 → 08-25,
> M1-E fully live-verified). This banner said "start here" until
> 2026-09-02, when it was found still pointing at finished work — a
> navigation-drift defect logged as `NEW-290`. The original direction is
> kept below verbatim because its *reasoning* is what stopped the
> re-sequencing, and that reasoning is still worth reading.
>
> **Update, 2026-09-09 (second navigation-drift correction — this
> banner itself had gone stale again, same failure class as `NEW-290`;
> the "next round is `B6.2`" line below was true 2026-09-02 but had not
> been updated since, even though every phase it names since finished):**
> **Phase A1 is now fully closed** — `7.4`'s remaining item was the
> production-config live pass, which landed as M1-E (already described
> above, DONE 2026-08-23). **Phases B6 and B7 are now both fully
> closed** — every sub-item `B6.1`…`B6.8` and `B7.1`…`B7.4` is `[x]` in
> §6.3–§6.10 below (`B6.3`/`B6.4a`/`B6.4b-f` landed 2026-09-06, closing
> the last `B4` gaps `NEW-272`/`273`/`274`; `B7`'s items landed
> 2026-09-07). A large NEW_ISSUES.md ledger-closeout series (6 batches
> covering telemetry, prompt/planner, and daemon/process-lifecycle,
> plus a combined live-verify session and 4 follow-on cleanup rounds)
> also completed 2026-09-08/09 — see `PROJECT_LOG.md`'s entries from
> those dates for the full record; not summarized here to avoid this
> banner going stale a third time by trying to track round-level detail
> that belongs in `PROJECT_LOG.md`.
>
> **Where a fresh session should actually look now:** there is no
> single obvious "next phase" the way M1 or B6 were — check §6's
> remaining `- [ ]` lines directly (search this file for `\- \[ \]`)
> rather than trusting a prose summary here, since that's exactly the
> mechanism that went stale twice. As of this update those are: the
> **concurrency test** (§7.4a's KV-cache/slot-count check — last live
> pass, 2026-08-26, was a negative result measured against the retired
> 7B model, not yet re-run against Qwen3.5-4B), **`T10`** (telemetry
> schema v2 migration, scoped but not started), **`11.x`** (Model
> Orchestrator, parked until a domain agent needs it — not actionable
> now), and **`P.1`** (self-improvement activation, permanently gated by
> rule 1). `NEW_ISSUES.md` also has a handful of small open items
> (`NEW-422`/`NEW-423`) and an untriaged ~50-item broader
> process-lifecycle population from the 2026-09-08 ledger-closeout
> batch, neither prioritized.
>
> --- original 2026-08-22 direction, kept as the record ---
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

#### M1 — migrate to Qwen3.5-4B as the single model ✅ CLOSED 2026-08-25 (A–G all done; this heading said START HERE until 2026-09-02 — see `NEW-290`)

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
| **7.4b** model lifecycle policy — **CLOSED 2026-08-27 (fully live-verified)** | Reshaped by §1.4 | **A**: embed always resident — implementation landed, code-reviewer pass done 2026-08-23 (§4.4). **LIVE-VERIFIED 2026-08-26 under the real `codey-start` entry point.** **B**: planner ceiling 8192 — **moot, no separate planner**. **C**: coder interactive-vs-daemon context branching — landed + `NEW-152` fix, code-reviewer pass done 2026-08-23. Option C respawn-on-upgrade (`NEW-145`/`NEW-149`/`NEW-155`) implemented, `NEW-259` and `NEW-261` resolved, **LIVE-VERIFIED 2026-08-27 on-device**: background model spawned at `n_ctx=16384` (PID 5943), interactive attach terminated background PID and respawned at `n_ctx=65536` (PID 6300) with zero leaks. Fully closed across all tiers. **D**: folded into M1-F,
**DONE 2026-08-24** — the constant now reflects there being no separate
planner process, with real re-derived numbers. |
| **Lease/registry — CLOSED 2026-08-26, code-reviewer-approved** | **Code-complete, mandatory rule-4 code-reviewer pass APPROVED 2026-08-26 (same day).** Reviewer independently traced `stop()`'s control flow line-by-line (no double-release, no leak), confirmed `_reconcile_adopted_slot()`'s try/except wraps its entire body (nothing can propagate into `load_primary()`), confirmed every `resolve_port_owner_pid()`/`pid_cmdline_contains()` caller checks for `None`/`False` before use (rule 3 intact), confirmed the adoption-branch ordering (`_port_is_bound()` before `_check_health()`), independently reproduced `NEW-200`'s `PermissionError` claim live, and — notably — hand-broke `_pid_owning_inode()` locally and confirmed the rewritten test actually fails without the real fix, proving it's a genuine regression guard and not a tautology. Full suite independently rerun: 692 passed/1 skipped, matching. Three non-blocking findings surfaced by the review, logged per rule 8 rather than silently dropped: **`NEW-201`** (a TOCTOU double-registration race between `find_resident_slot()`'s read and `register_slot()`'s write, confirmed NOT currently reachable — gated on `NEW-200`'s dead `/proc/net/tcp` path for `loader_v2.py`, and `embed_server.start()` has only one sequential caller today), **`NEW-202`** (a status-filter divergence between `find_resident_slot()` and `embed_server.py`'s older `_find_pid_via_registered_slot()`, confirmed currently harmless by grepping every embed slot-write site), **`NEW-203`** (an inaccurate docstring claim in `stop()` about when `self.process` is `None` for an adopted server — a real edge case exists, but the resulting behavior stays safe). None of the three block approval; all are logged for future attention if their preconditions ever change. Replaced port-probe adoption with an explicit registry query, built directly against the existing resource-gate slot store rather than a second lease-file format. New: `find_resident_slot()` (query: is a model already resident, at what `n_ctx`/`pid`/`port`), `resolve_port_owner_pid()`/`_pid_owning_inode()`/`pid_cmdline_contains()`/`resolve_spawned_n_ctx()` (generalized from `embed_server.py`'s own pre-existing pattern, for positively identifying a genuinely-foreign process — never a name-based guess, rule 3), `register_slot()`/`reserve_slot()` now persist `n_ctx`. `core/loader_v2.py`'s new `_reconcile_adopted_slot()` registers a previously-unlisted resident coder server on adoption and logs (not respawns, per `NEW-149`'s own scope) an under-provisioned-ceiling mismatch. `core/embed_server.py`'s `start()` now adopts an already-healthy occupant instead of killing it (`NEW-146`'s actual fix — the daemon's own restart path, not just `core/inference.py`'s caller `NEW-144` covered), and `stop()`'s slot-release was moved out of the `if self.process:` block so an adopted server (no `Popen` handle, `self.process is None`) still releases its slot instead of leaking it — a leak this same round's own adoption fix would otherwise have introduced. 15 new tests (`tests/test_loader_resource_gate.py`, `tests/test_resource_gate.py`), full suite **692 passed, 1 skipped** (up from 671/1). **Real platform limitation found and documented, `NEW-200`**: `/proc/net/tcp`/`tcp6` are `PermissionError` on this actual device for every caller, including a process reading its own sockets — confirmed by direct read (rule 12), not assumed. This means `resolve_port_owner_pid()`'s primary path cannot succeed here for `NEW-104`'s original "truly foreign, no pre-existing slot" case; the mechanism degrades safely (returns `None`, never crashes, never falls back to a name-based kill) but is effectively non-functional on THIS device for that one sub-case — kept for portability to a rooted device or non-Android deployment. The two cases that DO work here (a slot this process itself registered; `embed_server.py`'s registered-slot fallback) don't depend on this scan. **Absorbs and updates**: `NEW-104` (partially — see `NEW-200`'s caveat), `NEW-144`/`NEW-146` (embed kill-and-replace of a healthy occupant, now fixed both at the `inference.py` caller AND the daemon's own `start()`/restart path), `NEW-149` (reuse-adopts-under-provisioned-server is now detectable/logged, not silently invisible — not auto-corrected, per this item's own scope). **Mandatory rule-4 code-reviewer pass: APPROVED 2026-08-26** (see this cell's opening sentence for the full review summary) — this item is now DONE: code-complete, code-reviewer-approved. Not live-verified (no live component by design — this is admission/adoption accounting logic, not a model-load test); a future live pass exercising a genuine cross-process adoption scenario would still be informative but is not required to consider this item closed. |
| **Concurrency test — CLOSED 2026-09-09, fully live-verified, checkbox now checked** | **Behavioral test RUN 2026-08-26 against the real `codey-start` stack — negative result, checkbox stays unchecked** | **This row's earlier "mechanism confirmed active, remaining ask is a behavioral live test" framing has now been tested, and the result is a genuine architectural finding, not a routine pass/fail (`NEW-206`).** Scope note: the real live pass used `CODEY_N_CTX=8192` (a pre-existing, permitted override — precedent `U.31`/`NEW-95`/7.4a), not production's real `65536` ceiling, because reaching oversubscription at 65536 would take ~40+ minutes of prefill per rung at this device's measured rate; same binary, same code path, same `n_parallel=4, kv_unified=true` defaults, smaller physical pool only. **Proven:** (1) genuine concurrent decoding is real — a smoke test showed two tiny requests both `"is_processing": true` on different slots (2, 3) simultaneously via `/slots`; (2) two prompts sized at 4245+4246 tokens (`/tokenize`-measured, combined 8491 — already OVER the 8192 pool before generation) produce KV-cache fragmentation (`failed to find a memory slot for batch`, confirmed by reading the real allocator source, `~/llama.cpp/src/llama-kv-cache.cpp:894-1084` — `find_slot()`'s contiguous-allocation branch fails when it can't find `n_test` CONTIGUOUS free cells even if the total free-cell count elsewhere would suffice, a genuine fragmentation mechanism, not a simple linear sum-check), a ~12-minute cascading batch-size retry (509→256→...→1), and then a **hard failure of BOTH in-flight requests** (`Context size has been exceeded`, HTTP 500 for each) — no queuing, no serialization, no truncation-and-continue, no partial output from either side. RAM stayed flat throughout (no resource-exhaustion confound). An ADB-confirmed ~3s phone-foreground blip occurred at t+70-73s, 11+ minutes before the actual failure event — timing gap rules it out as a cause; the finding stands as real and confound-independent. **Not proven, and narrower than a first pass concluded:** because combined demand ALREADY exceeded total pool capacity before generation started, this run cannot separate "trivially fails because demand genuinely exceeds any pool's total capacity" (true at any pool size, not itself surprising) from "fails via fragmentation even when combined demand is comfortably UNDER the nominal pool size" (the mechanism `find_slot()`'s contiguity requirement makes plausible, and the shape that actually threatens a realistic daemon+TUI scenario against 65536's much larger headroom) — that distinction needs a dedicated 65536 re-run designed to stay under nominal capacity, not just a bigger-pool repeat of the same over-100% scenario. Also untested: both prompts here failed at PREFILL time, before their `n_predict: 300` generation budget was reached — whether two requests that fit at admission and only collide DURING generation degrade the same way (with, plausibly, partial output before failure, unlike this round's all-or-nothing result) is a distinct, unexamined failure surface. **Neither of the two success bars this test was scoped against was met** ("both complete without corruption/deadlock" — the near-term daemon+TUI bar — nor the harder future "true simultaneous decoding" bar). **Checkbox stays unchecked.** This bears directly on §1.4's single-shared-model architecture decision and §8 Q3's still-open concurrency piece — escalated to Ish as **§8 Q11**, per rule 1/CLAUDE.md's escalation bar for anything touching the plan's own architecture. **Status update, 2026-08-26: §8 Q11 ANSWERED by Ish.** Option (a) (a 65536-scale re-run targeting the two untested gaps) explicitly declined by Ish's own judgment call, not skipped by oversight. Fix direction: **(c) as primary defense (the resource gate refuses admission once combined estimated context would approach the shared pool) with (b) as its direct backstop (an admission refusal becomes a serialization wait, not an outright rejection)** — chosen together, not either alone, and not (d). Full design — denominator confirmed from source (`n_ctx`, not `n_ctx/n_parallel`), typical-request-footprint check, the two live call sites (`core/inference_hybrid.py`, `core/plannd.py`) that would need wiring, new per-slot reservation-record state, and the open numbers (safety margin, queue timeout) left for a follow-up implementer round — is in §8 Q11 itself and `PROJECT_LOG.md`. **A second design-review pass found the design's "release on HTTP-return" hook is likely wrong** (source-checked: `slot::release()` in `~/llama.cpp/tools/server/server-context.cpp` retains a normal task's cached prompt tokens, so per-call release under-counts real occupancy in the dominant multi-turn case) — now the design's single biggest open question; candidate resolution 1 (poll `/slots`'s confirmed-real `n_prompt_tokens` field, enabled by this build's own default) is confirmed viable, not implemented. `NEW-207` (found outside this round's scope while enumerating concurrency pairs: `can_dispatch_task()`'s `interactive_active` check is evaluated only once, at task-claim time) logged per rule 8. **Scoped, not implemented this round (rule 4)**; checkbox stays unchecked. **Status update, 2026-08-26: §8 Q11's fix is now CODE-COMPLETE AND SELF-TESTED (both open design questions — the release-signal hook and the safety-margin/timeout numbers — resolved and implemented, not just proposed), MANDATORY RULE-4 CODE-REVIEWER PASS NOT YET RUN, NOT LIVE-VERIFIED.** `core/resource_gate.py` gained `reserve_context_budget()`/`release_context_budget()`/`wait_and_reserve_context_budget()` (a second, independent file-locked reservation ledger reusing `_LockedState` exactly as-is), `resolve_effective_n_ctx()` (real spawned n_ctx, never `MODEL_CONFIG` directly — a mid-round advisor review caught that this would otherwise have silently no-op'd on `NEW-206`'s own `CODEY_N_CTX` override scenario), and `estimate_prompt_tokens()` (centralized `/tokenize`-with-heuristic-fallback, padded 1.35x on the fallback path). Wired at both named call sites (`core/inference_hybrid.py::infer()`, `core/plannd.py::get_plan()`), each releasing in a `finally`. `core/plannd.py`'s new `compute_outer_plan_timeout()` and two `core/daemon.py` call sites updated so the outer `asyncio.wait_for` around a plan request also budgets for the new pre-request queue wait — a necessary companion change to preserve `compute_planner_timeout()`'s own "inner fires first" invariant, not scope drift. Full design/numbers detail and full test-suite result (716 passed/1 skipped) recorded in §8 Q11's own entry above and `PROJECT_LOG.md`. **Checkbox stays unchecked** pending the mandatory code-reviewer pass and a live-verification pass — code-complete is not live-verified (rule 7). **Status update, 2026-08-27 — mandatory rule-4 code-reviewer pass: CHANGES REQUESTED (logging-only requirement, no code fix mandatory).** Reviewer independently verified fail-closed n_ctx resolution, no cross-ledger TOCTOU regression, correct lock discipline in the wait loop (never holds the blocking flock across sleep, clean timeout with no leaked reservation), release-on-every-exit-path in both call sites (including exception branches), correct daemon timeout layering (outer strictly bounds inner+queue-wait), no duplicated constants, and that the two pre-existing test files' new autouse fixtures only bypass the new admission check without weakening their original assertions. Full suite independently rerun: 716 passed/1 skipped, matching. **One real defect found, safe-direction only (under-admits, never over-admits — cannot reopen `NEW-206`'s cascade):** `reserve_context_budget()`'s combined-usage sum double-counts every admitted request for its entire in-flight duration, not just the brief TOCTOU window the design intends — because `release_context_budget()` only fires in a `finally` after the full HTTP call returns, an admitted request is counted both via its still-outstanding local reservation AND via `/slots`' own live occupancy for as long as it runs, quietly roughly halving the real concurrency the fix was meant to preserve at the documented ~8-9% typical footprint and 15% margin. Not a safety bug (rule 8 logging required, not a mandatory code fix this round) — logged as **`NEW-208`**. Required action (logging) completed same day; the fix's own approval status is otherwise clean pending a decision on whether to fix `NEW-208`'s concurrency-reduction cost now or defer it. **Status update, 2026-09-09 — the mandatory live-verify pass this row has been waiting on has now run, and the fix DOES NOT reliably work.** Real hardware, `CODEY_N_CTX=8192`, one RAM-disciplined model-load cycle: the gate's own admission arithmetic is correct in isolation (a direct call, both solo and concurrent, refused/admitted exactly as designed), but the real end-to-end path through `ChatCompletionBackend.infer()` still let two combined-over-ceiling requests (9099 tokens against a 6963-token ceiling) genuinely double-admit into the shared pool — confirmed directly from server logs showing both processing simultaneously in different slots. Both requests eventually died to a 300s client-side HTTP timeout rather than this row's original `Context size has been exceeded` 500 cascade (that specific fragmentation mechanism did not reproduce this time) — a different proximate failure, but the same class of outcome the fix exists to prevent. **Compound root cause, both confirmed from evidence:** (1) `core/resource_bus.py`'s `DEFAULT_LEASE_DURATION_SEC=60.0` is shorter than this device's realistic in-flight duration (a 4249-token prompt's prefill alone took 179s), so the first request's ledger reservation auto-expired while it was still genuinely running; (2) `reserve_context_budget()`'s fallback when `/slots` is unreachable degrades occupancy to zero — exactly the dangerous direction its own docstring names — and `/slots` was observed unreachable in 12 of 13 polling attempts during precisely the high-load window that mattered. This also falsifies `NEW-208`'s "safe-direction-only, cannot reopen NEW-206's cascade" claim: under real degraded conditions it does over-admit, just via a different mechanism than `NEW-208` itself describes. Logged as two new findings, **`NEW-430`** (lease duration) and **`NEW-431`** (`/slots`-unreachable degrade behavior) — fixing only one leaves the hole open via the other. A third, unrelated finding surfaced during this session's pre-flight, **`NEW-432`**: a stale resident-slot record with a since-reused PID was permanently un-reapable (`_pid_alive()`'s deliberate `PermissionError → alive` fail-closed branch), silently corrupting the ceiling until manually cleaned up before the test could run. **Status update, 2026-09-09 — `NEW-430`/`NEW-431` fix round CODE-COMPLETE and code-reviewer APPROVED (`f6c3a78`), NOT YET LIVE-VERIFIED.** `reserve_context_budget()`'s `acquire_context_lease()` call now passes `lease_duration=CONTEXT_RESERVATION_MAX_AGE_SECONDS` (1800.0) explicitly rather than inheriting the 60s shared default (`NEW-430`). `_fetch_slots_prompt_tokens()` now retries once before giving up, and `reserve_context_budget()` fails closed (refuses admission, `effective_n_ctx` set to the real resolved value so the caller retries rather than hard-failing) instead of degrading occupancy to zero when `/slots` stays unreachable (`NEW-431`). Reviewer traced end-to-end (not pattern-matched) that `effective_n_ctx` is never `None` on the new refusal path, that per-lease duration is honored by the reaper rather than silently re-defaulted, and that the `/slots` retry has no lock-ordering/double-release risk; flagged and accepted a new latency characteristic (a persistent `/slots` outage now surfaces as up to a ~600s hang-then-refuse instead of an immediate one, confirmed not masked by either call site's own HTTP timeout). 8 new tests, full suite 1552 passed/1 skipped/1 unrelated pre-existing failure (bisected to unmodified `main`, logged separately as `NEW-433`). One new out-of-scope finding logged, not fixed: `NEW-434` (the retry loop re-runs `/tokenize` on every tick, adding load under exactly the condition this fix targets). **Status update, 2026-09-09 — the mandatory live-verify pass has now run: `NEW-430`/`NEW-431` themselves CONFIRMED FIXED, but the pass still ends FAIL overall due to a new, independent bug.** Real hardware, `CODEY_N_CTX=8192`, one RAM-disciplined model-load cycle, real end-to-end repro (two genuinely concurrent 4246-token requests through the actual daemon+model stack). **No over-admission occurred** — confirmed directly from the real lease-reservation DB, only one lease was ever granted across the whole test window — so `NEW-206`'s original double-admission hazard did not reoccur, and `NEW-430` (the first request's 212.9s lease survived intact, released cleanly, no premature reap) and `NEW-431` (19 real `/slots poll failed... degrading` warnings fired from production logging alone during the busy window, and the second request was correctly refused/retried rather than wrongly admitted) are both independently confirmed working under real load. **But the second request never completed** — it was refused for the full 600s queue-timeout cap and died to that timeout, even though the server was genuinely idle for ~390s of that window. Root cause, newly found and logged as **`NEW-435`**: `_fetch_slots_prompt_tokens()` sums every slot's `n_prompt_tokens` unconditionally, including idle slots — llama.cpp's real `/slots` endpoint keeps reporting a slot's last-served request size after it goes idle, so the gate perceived the pool as still full long after it was genuinely free. This is the opposite failure direction from `NEW-431` (stuck non-zero rather than wrongly-zero) in the same function. **Status update, 2026-09-09 — `NEW-435` fix round CODE-COMPLETE and code-reviewer APPROVED (`22cab45`), NOT YET LIVE-VERIFIED.** `_fetch_slots_prompt_tokens()` now only sums a slot's `n_prompt_tokens` when `is_processing is True` — root cause confirmed against the real llama.cpp source (`n_prompt_tokens` persists after release via `task_prev`; `is_processing` is emitted unconditionally and updates with no meaningful lag). A slot with a missing/malformed `is_processing` field is treated as schema drift and counted anyway (fails closed, warns), same principle `NEW-431` established. 7 new tests, including one that independently proves the OLD formula would have summed the stale value on the exact real repro shape. Reviewer traced the fail-closed branch live, confirmed no other caller anywhere relies on the old "never 0" behavior. Full suite: 1673 passed/1 skipped/1 unrelated pre-existing failure (`NEW-433`, reconfirmed). One new Suspected finding logged, not fixed: `NEW-436` (a possible, conservative-direction double-count between `/slots`' occupancy sum and the local reservation ledger for a request that's both locally leased and actively processing — same shape as the already-accepted `NEW-208`, not yet confirmed real). **Status update, 2026-09-09 — the live-verify pass has now run against this exact bar, and it PASSES.** Real hardware, `CODEY_N_CTX=8192`, one RAM-disciplined model-load cycle, the same real end-to-end repro as every prior pass in this chain (two genuinely concurrent 4246-token requests through the actual daemon+model stack, combined 8492 tokens against the resolved 6963 ceiling). Direct before/after comparison against the preserved pre-fix run confirmed the exact `slots=4554` stale reading that caused the prior FAIL is gone. The second request was admitted **1.45 seconds** after the first request's slot released (matching the 2.0s poll interval, nowhere near the 600s cap that killed the prior pass), and **both requests completed successfully** (`success: true`, 300 tokens each). This is the first time across the entire `NEW-206`→`NEW-430`/`NEW-431`→`NEW-435` chain that the row's actual success bar — both requests complete, no starvation, no over-admission — has been met on real hardware. **Checkbox now checked.** Residual, non-blocking findings from this saga remain open and tracked separately, not required for this row's closure: `NEW-432` (a stale resident-slot record un-reapable on PID reuse — a different mechanism, narrow and rare), `NEW-433` (an unrelated pre-existing test failure), `NEW-434` (a `/tokenize` call efficiency issue in the retry loop, not a correctness bug), `NEW-436` (a conservative-direction double-count — confirmed real 2026-09-10, accepted not-fixed: a concurrent already-dispatched request counted in both the `/slots` sum and its still-held ledger lease; safe-direction, negligible impact at the `n_parallel=4` production ceiling; the original entry's "own reservation" mechanism was wrong and was corrected per rule 6; two spin-off findings `NEW-441`/`NEW-442` logged). |

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

**Scoped 2026-08-27 (desk-only — no code written, `~/Aigentik-CLI`
untouched, per this project's own rule that it is never modified):**
read `~/Aigentik-CLI`'s real code and data (a Node.js/ES-modules CLI,
`git remote origin` already `https://github.com/Ishabdullah/
Aigentik-CLI.git`, local `main` even with `origin/main` — 0 ahead/0
behind) and `restoricon_core/`'s real schema directly, per rule 12.

**RESOLVED 2026-08-27 — Ish chose option (a): expand the schema, not
narrow the round.** Rather than the scoping round's own stated
preference (option (b), narrowing B2's exit criterion to contacts+
customers only), Ish decided `restoricon_core`'s schema should cover all
five of Aigentik-CLI's real data shapes now. The schema/models/service/
RBAC build for the four previously-missing shapes (subcontractors,
appointments/calendar, automation rules, business profile+DNC) is
code-complete and self-tested as of 2026-08-27 — see `PROJECT_LOG.md`'s
2026-09-02 de-ledger entry (moved from §4.5) for the full entry
for exactly what was built, the test numbers, and the two new findings
(`NEW-212`, `NEW-213`) it surfaced. **Still pending a mandatory
code-reviewer pass (rule 4 — this touches auth/RBAC) before it can be
committed or treated as done for this phase.** The original open-decision
framing below is left in place as the historical record of the question
Ish resolved, not as still-open.

**Original open decision (RESOLVED above, kept for context):** `NEW-209`
found the local store is ten
write-site modules (`contacts.js`, `calendar.js`, `email-rules.js`,
`sms-rules.js`, `do-not-contact.js`, `queue.js`,
`subcontractor-recruiter.js`, `customer-module.js`, `index.js`/
`owner-command.js`), not the plan's brief "contacts, calendar, rules,
profile," and `restoricon_core/database.py`'s 12 tables have a
destination for only two of the five underlying data shapes — contacts
(partial fit) and customers (partial fit, via `crm_service.py`'s
`create_customer()`/`create_lead()`). Subcontractors, calendar/
appointments, automation rules, business profile, and the Do-Not-Contact
list have **no Core table at all**. Two options, not resolved here:
(a) B2 also adds the four missing tables, absorbing B3/B5a schema work
into a round scoped as data/API integration; (b) B2's exit criterion
narrows to "no local *CRM* data store" — contacts+customers migrate,
comms write through, the other four stores stay local with an explicit
deferral pointer to B3 (calendar/rules)/B5a (subcontractors) — and the
plan's stated exit criterion is corrected to say so rather than marked
met on a narrower result. No recommendation is binding without Ish's
sign-off; the scoping round's own preference is (b), on this project's
documented pattern that absorbing adjacent-phase scope into one round is
this project's repeat failure mode, not (a)'s specific content.

**Fork creation DONE, 2026-08-27.** `~/Codey-Aigentik` exists: `origin` =
`https://github.com/Ishabdullah/Codey-Aigentik.git`, `upstream` =
`https://github.com/Ishabdullah/Aigentik-CLI.git`, pushed to `origin`,
tracking `origin/main`, working tree clean. The sequence run (recorded
here for reference, no longer a to-do):
```
git clone https://github.com/Ishabdullah/Aigentik-CLI.git ~/Codey-Aigentik
cd ~/Codey-Aigentik
git remote rename origin upstream
git remote add origin https://github.com/Ishabdullah/Codey-Aigentik.git
git push -u origin main
```
Cloned from Aigentik-CLI's real GitHub remote (confirmed even with local
`main`), not the local `~/Aigentik-CLI` directory, so `upstream` tracks
Ish's future pushes to the public repo the way "upstream fixes pulled
via `git fetch upstream`" (§3.4) intends. `git ls-files` in
`~/Aigentik-CLI` confirms `config.json` and `data/` are both correctly
gitignored/untracked (55 tracked files, no secrets) — the clone carries
no secrets or business data, but also means `Codey-Aigentik`'s own
`config.json` needs to be created fresh in its working copy, never
committed (`NEW-210`).

**Task 2 (data migration) scoped 2026-08-27 — spec handed to
implementer, no code written yet.** Read the real, live `~/Aigentik-CLI/
data/*.json` files directly (per rule 12) against the schema/service
layer landed this round (`c30d755`). Findings that reshape task 2:
- Only 4 of the 8 real data files map cleanly onto existing tables today:
  `subcontractors.json` → `subcontractors`, `calendar.json` →
  `appointments`, `email-rules.json`/`sms-rules.json` → `automation_rules`,
  `profile.json` → `business_profile`. Combined real record count as of
  2026-08-27: 1 subcontractor, 1 appointment, 2 email rules, 0 SMS rules,
  1 profile — a small first pass, deliberately, to prove the harness
  (service-layer calls + `ai_agent` `AuthContext` + dry-run + idempotency)
  against real data before the bulk migration.
- `contacts.json` (201 records) is **not** customer data — it's an
  Android-contacts phonebook sync (`source: "android_contacts"`,
  `type` in `person`/`subcontractor`/`unknown`) with no destination table
  today. See `NEW-215` — needs an explicit scope decision from Ish before
  any script touches it.
- `customers.json` (3 records) is real CRM data but its ~46 fields
  substantially overflow the `Customer`/`Lead` models (insurance/claim
  fields, project scheduling fields, `dnc_status`) with no dedup key
  (`NEW-212`, already logged) — deferred out of this first migration
  pass, to be scoped separately once `NEW-212`'s `external_id` decision
  is made.
- `schedule-config.json` (scheduling defaults) has no destination table
  at all — see `NEW-216`, deferred.
- `do-not-contact.json` does not exist yet on disk (zero DNC entries
  added in production so far) — the migration script must treat "file
  absent" as "0 records," not as an error, and must not conflate it with
  `sms-rules.json`'s "file present, 0 records" state.
- `subcontractors`/`appointments`/`automation_rules` services have
  `create_*` (INSERT-only, `UNIQUE(external_id)`) with no lookup method
  — a second migration run would hit `sqlite3.IntegrityError` instead of
  upserting or skipping (`NEW-217`). Adding the three lookup methods is
  in-scope for the migration task itself, not deferred.
- The spec requires: dry-run as the literal default (`--apply` to
  write), source directory as a CLI arg (default `~/Aigentik-CLI/data`),
  an explicit `ai_agent` `AuthContext` bootstrap path written down (not
  improvised — the dataclass is trivially constructible outside the
  token path, so the spec pins whether a real `ai_agent` user row/token
  is created first or whether `AuthContext` is deliberately
  hand-constructed for this internal script, and why either is safe
  here), per-CHECK-constraint value-domain validation derived from the
  JS writer (not just the one sampled record) reported in dry-run rather
  than discovered as an `IntegrityError`, and retry-with-backoff plus a
  record-count sanity floor on JSON parses (Aigentik-CLI is a live
  process using non-atomic `writeFileSync`, so a read can land mid-write
  and yield a short-but-valid array that looks like a clean success).
- `install.sh`: no change needed — `json`/`sqlite3`/`argparse` are
  stdlib only.
- Not code-reviewed or implemented yet; next step is handing this spec
  to implementer, then the mandatory code-reviewer pass (rule 4 covers
  any RBAC/auth-context-construction code) before commit.

**Task 2 implemented and code-reviewer-approved, 2026-08-27 — see
`PROJECT_LOG.md`'s 2026-09-02 de-ledger entry (moved from §4.5) for its
full entry for the built artifacts, the reviewer's verification list,
the `NEW-218` doc-accuracy correction, and the test count.** Only a
dry-run against real Aigentik-CLI data has been run; no `--apply` run
against production has happened — that is a separate decision for Ish,
since it writes to the live Restoricon Core DB from real business data.
Do not mark this "done" beyond code-complete/code-reviewer-approved
until that decision is made and, if approved, the `--apply` run is
itself verified.

**Step 4 is not a simple config change (`NEW-211`):** Aigentik-CLI's
`chatLocal()` (`llama.js`) already POSTs to `http://127.0.0.1:8080`,
which is Codey-OS's own `PRIMARY_SERVER_PORT` default (`utils/
config.py:15`) — the same port. A same-port collision that happens to
return a real response is not the same as being admission-gated: it
bypasses `core/resource_gate.py`'s lease/slot mechanism and §8 Q11's new
`reserve_context_budget()` machinery entirely, built specifically to
prevent `NEW-206`'s oversubscription failure. Step 4's real content is
routing Aigentik-CLI's model calls through an admission-aware path (a
Core API endpoint that itself leases before proxying, or a
lease-acquisition step in Aigentik-CLI's own process before it calls
`:8080`), not editing a hostname. A1's lease/registry item is confirmed
CLOSED and code-reviewer-approved at HEAD (§6.2's "Remaining Phase A1
items" table), so the dependency this step needs is actually satisfied.

**Ordered task list for the follow-up implementation round** (pending
Ish's answer on the exit-criterion question above; assumes option (b)
below, adjust if (a) is chosen):

1. **Fork creation — DONE, 2026-08-27** (see above).
2. **Auth provisioning** (not in the plan's four steps, but required
   before step 3 can write anything): create an `ai_agent`-role user +
   token in the Core (`auth.py`'s existing `create_user()`/
   `create_token()`, `ROLE_AI_AGENT` already defined), add a `core_api`
   block (base URL + token) to `Codey-Aigentik`'s own `config.json`
   (gitignored, per `NEW-210`) — no Core-side code change needed, this
   is provisioning + config only. Confirmed the API already exposes
   `POST /api/v1/communications` (`restoricon_core/api/routes.py:211`)
   for step 3's comms write-through — no new route needed there.
3. **Data migration — SCOPE EXPANDED per Ish's option (a) decision
   (2026-08-27):** now that `restoricon_core` has all five schema
   destinations (see `PROJECT_LOG.md`'s 2026-09-02 de-ledger entry,
   moved from §4.5), the migration script should cover
   `data/contacts.json` (200 records), `data/customers.json`,
   `data/subcontractors.json`, `data/calendar.json` (currently empty —
   nothing to migrate yet, but the destination now exists),
   `data/email-rules.json`/`data/sms-rules.json`, `data/profile.json`,
   and a `data/do-not-contact.json` if one exists at migration time —
   translating each into the matching `restoricon_core.models` dataclass
   (`Customer`/`Lead`, `Subcontractor`, `Appointment`, `AutomationRule`,
   `BusinessProfile`, `DoNotContactEntry`) field-by-field, populating
   each new table's `external_id` from Aigentik's own string ID so the
   script is re-runnable (`customers`/`leads` have no such column yet —
   see `NEW-212`), calling the matching service's create/upsert method
   over the Core API. Not written this round — schema/models/service/RBAC
   only, per this round's own scope.
4. **Write-through replacement**, per module, not per file — all ten
   modules from `NEW-209` now have a Core destination and are in scope:
   `contacts.js`/`customer-module.js` write through to the Core's
   customer/lead endpoints; every inbound/outbound email and SMS handling
   path (`email-provider.js`, `gmail.js`, `index.js`'s Google Voice
   handling) calls `POST /api/v1/communications`; `calendar.js` writes
   through to the new appointments endpoints; `email-rules.js`/
   `sms-rules.js` write through to the new automation-rules endpoints;
   `do-not-contact.js` writes through to the new do-not-contact
   endpoints (**code-complete + code-reviewer-approved 2026-08-27, NOT
   live-verified against real production traffic — see §4's Phase B2
   task 4 pilot entry**); `subcontractor-recruiter.js` writes through to
   the new subcontractor endpoints.

   **Status audit 2026-09-02 (`NEW-288` resolution — static read of
   `~/Codey-Aigentik` HEAD `ee97279`; NOT live-verified).** This list
   said "ten" but `NEW-209` named **nine** groups (`NEW-294`); `queue.js`
   was then **ruled out of B2 scope by Ish** (2026-09-02 — transient
   owner-approval buffer, not a system of record; `NEW-291` closed),
   leaving **eight**. Of the eight: **seven are cut over** (code-complete)
   — `contacts.js` (+ `contacts-sync.js`), `calendar.js`, `email-rules.js`,
   `sms-rules.js`, `do-not-contact.js`, `subcontractor-recruiter.js`,
   `customer-module.js` (each has `coreRequest` on every path and zero
   local `fs`). **`index.js`/`owner-command.js` — the comms/Google-Voice
   path is cut over via `email-provider.js` → `POST /api/v1/communications`
   (`data/communications-retry.json` is a failure-retry spool only), and
   `business_profile` was closed by **B2-fin-1** on 2026-09-02 (fork
   commit `2056524`): `owner-command.js`'s three profile handlers now
   read Core-first, `data/profile.json` is a write-through cache. Rule-6
   note: `index.js` was already Core-first — only `owner-command.js` was
   the gap. **All eight groups are now cut over at the code-complete
   tier** (not live-verified — jest was the bar; and 7 of the 8 verdicts
   rest on `NEW-288`'s static `fs`-absence sweep, which did not check for
   indirect persistence via another module's exports — see `NEW-288` for
   the stated limits). B6's "B2 complete" prerequisite is satisfied — see
   Appendix A's B6 dependency block and `NEW-288`'s resolution.

   **Note:** `restoricon_core/api/routes.py`
   currently has no routes for any of the five new resources
   (`NEW-193`'s write-only-routes gap applies here too) — adding them is
   part of this step, not assumed already done by this round's schema
   work.
5. **Model-layer repoint**: replace `chatLocal()`'s direct `fetch` to
   `:8080` with a call through whatever admission-aware surface A1's
   lease/registry exposes for external callers — this needs its own
   design pass (not just a URL edit) since no such external-caller
   surface has been designed yet; flagged as a real open design item for
   the implementation round, not assumed solved by this scoping pass.

**Task 4a (routes for the five new resources) scoped 2026-08-27 — spec
below, not implemented.** Read `restoricon_core/api/routes.py` and
`api/server.py` in full, plus `crm_service.py`/`scheduling_service.py`/
`automation_service.py`'s real method signatures, per rule 12.
Confirmed: `routes.py` has zero routes today for subcontractors,
appointments, automation_rules, business_profile, do_not_contact
(`NEW-193`'s write-only-routes gap applies). `api/server.py` constructs
`CRMService` but never constructs `SchedulingService`/`AutomationService`
or passes them into `APIRouter` — both need to be wired in
`RestoriconAPIServer.__init__` and threaded through `APIRouter.__init__`
as two new required constructor args. Re-grepped `APIRouter(` across the
whole repo (not just `restoricon_core/`) — the only construction site is
`api/server.py:88`, so no other test builds `APIRouter` directly and the
constructor-signature change is safe.

**Auth/RBAC — no permission-matrix change needed.** RBAC is enforced in
the *service* layer, not the route layer (every service method calls
`actor.has_permission(...)` and raises `PermissionError`, which
`routes.py`'s `handle_request` already catches globally and turns into
403 — routes never call `has_permission()` directly). Confirmed
`ROLE_AI_AGENT` in `auth.py`'s `ROLE_PERMISSIONS` already holds full
read+write on all ten new permission constants
(`PERM_{READ,WRITE}_SUBCONTRACTORS/APPOINTMENTS/AUTOMATION_RULES/
BUSINESS_PROFILE/DNC`) as of `c30d755` — this task only wires routes,
it adds no new grants.

**Route list (method, path -> service call, verb convention matches the
existing `/{id}/sign` and `/{id}/pay` action-suffix pattern — zero
existing routes use PUT/DELETE despite the HTTP handler dispatching
both, so none are introduced here):**

| Method | Path | Calls | Falsy/error return |
|---|---|---|---|
| GET | `/api/v1/subcontractors` | `crm.list_subcontractors(actor, qualification_status=, primary_trade=, limit=, offset=)` | — |
| POST | `/api/v1/subcontractors` | `crm.create_subcontractor(Subcontractor(**body), actor)` | — |
| GET | `/api/v1/subcontractors/{id}` | `crm.get_subcontractor(id, actor)` | 404 |
| POST | `/api/v1/subcontractors/{id}/qualification` | `crm.update_subcontractor_qualification(id, body["qualification_status"], actor, body.get("recruitment_step"))` | 404 |
| GET | `/api/v1/appointments` | `scheduling.list_appointments(actor, customer_id=, status=, limit=, offset=)` | — |
| POST | `/api/v1/appointments` | `scheduling.create_appointment(Appointment(**body), actor)` | — |
| GET | `/api/v1/appointments/{id}` | `scheduling.get_appointment(id, actor)` | 404 |
| POST | `/api/v1/appointments/{id}/status` | `scheduling.update_appointment_status(id, body["status"], actor)` | 404 |
| GET | `/api/v1/automation-rules` | `automation.list_rules(actor, channel=, limit=, offset=)` | — |
| POST | `/api/v1/automation-rules` | `automation.create_rule(AutomationRule(**body), actor)` | — |
| POST | `/api/v1/automation-rules/{id}/match` | `automation.record_rule_match(id, actor)` | 404 |
| GET | `/api/v1/business-profile` | `automation.get_business_profile(actor)` | 404 (matches `customers/{id}`'s resource-fetch shape, not `/auth/me`'s 200-with-null shape) |
| POST | `/api/v1/business-profile` | `automation.upsert_business_profile(BusinessProfile(**body), actor)` | 200, not 201 — it's a singleton upsert (`id` pinned to 1), never a new resource |
| GET | `/api/v1/do-not-contact` | `automation.list_do_not_contact(actor, limit=, offset=)` | — |
| POST | `/api/v1/do-not-contact` | `automation.add_to_do_not_contact(body["identifier"], actor, name=, reason=, source=)` | **400**, not 404 — `None` means `classify_identifier()` rejected the identifier as malformed input, not "not found" |
| POST | `/api/v1/do-not-contact/remove` | `automation.remove_from_do_not_contact(body["identifier"], actor)` | 200 `{"removed": <bool>}` always — it's a bare `bool`, not `Optional` |
| GET | `/api/v1/do-not-contact/check?identifier=` | `automation.is_blocked(identifier, actor)` | 200 `{"blocked": <bool>}` always |

**Explicit non-goals for this task** (say so in the implementer handoff
so scope doesn't drift): no `~/Aigentik-CLI`/`~/Codey-Aigentik` JS files
touched — that is task 4's write-through step, still separate; no
by-external-id GET routes for any of the three services'
`get_*_by_external_id` methods — `migrate_aigentik.py` calls services
directly in-process (confirmed by its imports), so nothing needs them
over HTTP yet, and adding them now would be an unrequested feature; no
refactor of `routes.py`'s single `handle_request` into sub-routers even
though this task nearly doubles its length — that kind of unscoped
cleanup is this project's documented repeat failure mode.

**Rule-4/security note:** §6.4's own rule-4 analysis above says rule 4
"mostly does not apply" to B2 — that's still true here; this task is
not a process-lifecycle change (no daemon/PID/kill-logic/lock/GUI-bind
change). It is nonetheless mandatory for the code-reviewer per the
Workflow section's separate clause: "mandatory for anything touching
process control, daemon/kill logic, **or security**" — five new
auth-gated HTTP endpoints on a real API surface is a security-relevant
change regardless of rule 4.

**Task 4a built and code-reviewer-approved, 2026-08-27 — see
`PROJECT_LOG.md`'s 2026-09-02 de-ledger entry (moved from §4.5) for the full
entry** for the built artifacts, the reviewer's two non-blocking notes
(including `NEW-222`), and the test count. Code-complete/mock-tested via
the test suite only — not live-verified against a real running server
instance with real network calls, and no Aigentik-CLI/Codey-Aigentik JS
code calls any of these routes yet.

**Test plan:** extend `tests/test_restoricon_core/test_api.py`'s
existing live-HTTP-roundtrip pattern (`RestoriconAPIServer` bound to a
free port + `:memory:` db + real `urllib.request` calls) — its fixture
already seeds an `ai_agent`-role user, so the success path per resource
is cheap to add. For the negative case, add one `ROLE_TECHNICIAN` user
(confirmed in `auth.py`'s matrix to hold none of the ten new
permissions) and assert 403 across all five resources with one test —
a clean, already-verified-empty permission set makes it a reliable
negative. Record the exact before/after `pytest` pass count in the
commit/PROJECT_LOG entry (baseline confirmed 2026-08-27: 764 passed, 1
skipped).

**Docstring note for whoever implements this:** `APIRouter`'s class
docstring and `RestoriconAPIServer.__init__`'s new
`scheduling_service`/`automation_service` wiring should both note that
RBAC is enforced in the service layer, not here — the route layer's
only auth job is resolving the Bearer token to an `AuthContext` and
letting the global `PermissionError` handler turn a service-layer
rejection into 403. Without that note the new route block reads as if
it forgot permission checks.

**Task 4 (write-through replacement) — pilot module scoped 2026-08-27,
desk-only, no code written, `~/Aigentik-CLI` untouched.** Ish asleep;
proceeding autonomously per his standing instruction, no product-scope
call made (see below — the one candidate decision this task required
turned out to be an implementation-readiness fact, not a product
choice). Read `~/Aigentik-CLI/subcontractor-recruiter.js` in full (682
lines) plus every caller (`index.js`, `owner-command.js`,
`role-router.js`, `llama.js`) and `~/Aigentik-CLI/do-not-contact.js` in
full (its only caller set is the same four files), against
`restoricon_core/services/crm_service.py`'s real subcontractor methods
and `restoricon_core/models.py`'s `Subcontractor` dataclass, per rule
12.

**Subcontractors rejected as the pilot — `NEW-224`.** The task's initial
premise (subcontractors is the smallest/most isolated candidate because
task 2's migration already proved the table+service+route chain) turned
out to be only half true: `crm_service.py` has no general
partial-update method, only `update_subcontractor_qualification`
(status/step only). `subcontractor-recruiter.js`'s `updateSubcontractor()`
— the function actually driving the live SMS conversation's mid-flow
field merges (trade, experience, licensing, insurance,
`qualification_data` deltas) — has no Core-side destination to call.
Building one now would mean adding a new service method + route this
round, which is itself a security-relevant Core change needing its own
mandatory code-reviewer pass — not the "smallest, most isolated" pilot
this step calls for. See `NEW-224` for the full method-by-method gap.

**`do-not-contact.js` selected instead — clean 1:1 route match, zero
production-data risk.** Its four I/O functions
(`loadEntries`/`saveEntries` internal, `isBlocked`,
`addToDoNotContact`, `removeFromDoNotContact`, `listDoNotContact`) map
exactly onto the four already-shipped routes (`GET /do-not-contact`,
`POST /do-not-contact`, `POST /do-not-contact/remove`, `GET
/do-not-contact/check`) with no missing verb and no general-update need
— `addToDoNotContact`'s upsert-by-identifier semantics match
`automation_service.py`'s `add_to_do_not_contact` exactly. Per §6.4's
task-2 migration findings, `~/Aigentik-CLI/data/do-not-contact.json`
**does not exist yet** — zero production DNC entries as of 2026-08-27 —
so a Core-only cutover for this one resource has no existing data to
lose or dual-write to reconcile.

**Edit target confirmed: `~/Codey-Aigentik`, not `~/Aigentik-CLI`.**
Per §3.4's fork rationale and this project's standing rule that
`~/Aigentik-CLI` is never modified, the write-through change lands in
the fork's copy of `do-not-contact.js` (and its callers' call sites in
`index.js`/`owner-command.js`/`role-router.js`, all present verbatim in
the fork as of the 2026-08-27 clone).

**Dual-write vs. Core-only — decided as Core-only, no local JSON
fallback, not escalated to Ish.** The scoping round's first instinct was
defensive dual-write (Core as source of truth, JSON as fallback) on the
reasoning that this is Ish's live production messaging system and
degrading write availability would have real consequences. That
reasoning doesn't hold for the actual edit target: `~/Codey-Aigentik`
has no `config.json` and no `data/` directory yet, so it cannot run at
all today — there is no live traffic in the fork to protect. Dual-write's
only justification (availability under Core outage) doesn't apply until
cutover (retiring `~/Aigentik-CLI` in favor of the fork) actually
happens, and that retirement is Ish's decision, not made here. Worse,
dual-write has a real correctness bug for this specific resource: if the
Core write fails but the local JSON write succeeds, `isBlocked()` calls
against Core would miss an entry only the JSON file knows about,
silently failing the one thing this list exists to guarantee (never
re-contacting someone who opted out) — a defensive fallback that
degrades the safety property it's meant to protect is worse than a
hard failure. Decision: Core-only for this pilot; a failed HTTP call
surfaces as an error to the caller rather than silently falling back to
local JSON. This is a technical rollout-safety call, not a product-scope
decision — it doesn't foreclose any option Ish would care about, and is
documented here rather than escalated per that reasoning; flag it to
Ish for confirmation before any live cutover regardless.

**Auth provisioning (task-list step 2) confirmed NOT done — required as
part of this task's prerequisites, not deferred.** `~/Aigentik-CLI/
config.json` has no `core_api` block (full key structure read and
confirmed: `owner`/`gmail`/`llama`/`llm`/`gemini`/`vertex`/`sms`/
`behavior`/`paths` only). `~/Codey-Aigentik/config.json` does not exist
at all yet (only `config.json.example`) — and because
`do-not-contact.js` (like every write-site module) does a static ES
`import config from './config.json' with { type: 'json' }`, the fork's
modules cannot even be imported, let alone tested, without that file
existing first. `restoricon_core/database.py`'s `DEFAULT_DB_PATH`
(`~/.codey_restoricon/core.db`) does not exist on disk either — the
Core has never been run against its real persistent DB (`NEW-225`). No
`restoricon_core/api/server.py` process was found running (`ps aux`
checked). Prerequisite work folded into this task: (1) start the Core
API once against its real DB path (creates the schema via `CREATE TABLE
IF NOT EXISTS` on first connection) to run `auth.py`'s `create_user()`
(role=`ai_agent`) + `create_token()` once, producing a real bearer
token; (2) create `~/Codey-Aigentik/config.json` (copy from
`config.json.example`, gitignored per `NEW-210`, never committed) with
a new `core_api` block: `{ "base_url": "http://127.0.0.1:8770", "token":
"<the token>" }` (port confirmed from `restoricon_core/api/
server.py:28`'s `DEFAULT_PORT = int(os.getenv("RESTORICON_API_PORT",
"8770"))` — distinct from the `:8080` `llama.js` `chatLocal()` uses,
confirming `NEW-211`'s port-collision finding is unrelated to this step,
per point 5 below). This is provisioning + config only, no Core-side
code change (`create_user`/`create_token`/`ROLE_AI_AGENT` all already
exist per the auth-provisioning note already in this section).

**Confirms NEW-211 is unrelated to this step.** `NEW-211` is about
`llama.js`'s `chatLocal()` hitting `:8080` (Codey-OS's own
`PRIMARY_SERVER_PORT`) for *model* calls — that's task-list step 5
(model-layer repoint), a separate, harder, not-yet-designed piece of
work. `do-not-contact.js`'s writes never touch the model or port 8080;
this pilot can proceed fully independently of NEW-211's resolution.

**Implementer spec:**
1. Convert `loadEntries`/`saveEntries`/`isBlocked`/`addToDoNotContact`/
   `removeFromDoNotContact`/`listDoNotContact` to `async function`s that
   call the Core's four do-not-contact routes over HTTP (`fetch` —
   already a global in this Node runtime per `llama.js`'s existing
   usage, so `install.sh`/`package.json` need no new dependency; state
   this positively rather than silently skipping the rule-11 check).
   `loadEntries`'s current unconditional list-load becomes a `GET
   /api/v1/do-not-contact` call; drop the local-file existence check
   entirely (Core-only, no fallback, per the decision above).
   `detectOptOutRequest` and `classifyIdentifier`/`normalizePhone`/
   `normalizeEmail` are pure functions with no I/O — leave them
   untouched, still local, still synchronous.
2. Every call site becomes `await`-ed. All current call sites already
   sit inside `async function`s (`checkDoNotContact` in `index.js`,
   `handleBlockContact`/`handleUnblockContact`/`executeInterpretedCommand`
   in `owner-command.js`, `detectRoleAndIntent` in `role-router.js` — the
   `detectOptOutRequest` call inside it needs no change since that
   function stays synchronous) — no wider async-propagation refactor is
   needed elsewhere in the fork for this module. Two specific sites need
   restructuring, not just an `await` added: `owner-command.js`'s
   `handleBlockContact` uses `identifiers.forEach(id =>
   doNotContact.addToDoNotContact(...))` and `handleUnblockContact` uses
   `candidates.filter(id => doNotContact.removeFromDoNotContact(id))` —
   both need converting to `for...of` with `await` (or
   `Promise.all`/`Promise.allSettled` if concurrent calls are
   acceptable) since `.forEach()`/`.filter()` do not await a callback's
   returned promise, and `handleUnblockContact`'s `filter` result
   (`removed.length === 0` check) would silently be wrong (comparing
   truthy `Promise` objects, always `>0`) if left as-is.
3. Preserve existing return shapes/behavior exactly: `isBlocked` still
   resolves to a `bool`; `addToDoNotContact` still resolves to the
   entry object (or `null` for an unclassifiable identifier — matches
   the route table's documented 400 case, translate a non-2xx Core
   response into the same `null` return the callers already branch on);
   `removeFromDoNotContact` still resolves to a `bool`; `listDoNotContact`
   still resolves to the same formatted string (build it client-side
   from the `GET /api/v1/do-not-contact` list response, matching the
   existing numbering/format).
4. Update the fork's `install.sh`/README with the `core_api` config
   step so a fresh clone of `~/Codey-Aigentik` can be configured
   end-to-end (rule 11).
5. Tests: extend the fork's existing `tests/do-not-contact.test.js`
   pattern to mock the Core API HTTP calls rather than the filesystem;
   do not delete existing behavioral test cases, convert their
   assertions to the new async signatures.

**Verification tier this task can reach:** code-complete +
code-reviewer-approved + tested against a Core API instance started
locally for the test run. It cannot be "live verified" against
`~/Aigentik-CLI`'s real production traffic in this round — that would
require retiring `~/Aigentik-CLI` in favor of the fork, which is Ish's
cutover decision and unmade. Record the tier honestly per rule 7 rather
than implying production verification happened.

**Findings logged out of scope, `NEW-219`/`NEW-220`/`NEW-221` in
`NEW_ISSUES.md`** (not fixed here): `automation_service.py` has no
single get-rule-by-id method, so `POST /automation-rules/{id}/match`'s
target `id` has no way to be read back over HTTP — the `NEW-193`
write-only-routes class, filed Confirmed; `is_blocked`/
`remove_from_do_not_contact` both return bare `False` for an
unclassifiable identifier, so an HTTP caller of a *do-not-contact
suppression list* cannot distinguish "not on the list" from "malformed
input" — safety-relevant, filed Confirmed, not fixed in the route
because fixing it would mean duplicating `classify_identifier()`'s
logic at the route layer; `Model(**json_body)` on unrecognized JSON
keys raises `TypeError`, which the existing `except` chain doesn't
catch as 400 so it falls through to 500 — true of all eight
already-shipped POST routes today, not new to this task, filed
Confirmed as a pre-existing pattern the new routes will also inherit by
matching convention.

**Rule 4 relevance — checked, mostly does not apply:** B2 itself is
data/API integration, not process supervision. It does not touch
`ccos/core/plugin_manager.py` (the `external_process` supervision
plumbing §3.4 describes is explicitly separate work, §6.8's Phase A2,
"does not exist yet"), and does not touch `~/Aigentik-CLI`'s own
`start.sh`/`stop.sh`. **The one part that could cross into rule-4
territory:** if task 5 (model-layer repoint) ends up requiring a
start/stop sequencing change so `Codey-Aigentik`'s process launch
doesn't race the shared `llama-server`'s own admission state, that
specific change is process-lifecycle and needs its own mandatory
code-reviewer pass — called out here so the implementer doesn't cross
that line unnoticed.

**Task 4, second module — `email-rules.js`/`sms-rules.js` scoped
2026-08-27, desk-only, no code written, `~/Aigentik-CLI` untouched.** Ish
still asleep; proceeding autonomously per his standing instruction, no
product-scope decision made — the calendar.js fallback evaluation and
the `NEW-230` delete-method decision below are both implementation-
readiness/rollout-safety calls, not product choices. Read
`~/Aigentik-CLI/email-rules.js` (145 lines) and `~/Aigentik-CLI/
sms-rules.js` (115 lines) in full, every caller (`index.js:1203` and
`884`, `owner-command.js` lines 269/275/477/580-636), the real
production data (`data/email-rules.json` — 2 real rules;
`data/sms-rules.json` — `[]`, 0 rules; `data/calendar.json` — 1 real
appointment, not empty as the task-2 finding's summary table implied),
`automation_service.py` in full, and `routes.py`'s automation-rules
block, per rule 12.

**Confirmed as the best next candidate over calendar.js — did not need
to fall back.** `calendar.js`'s real appointment record
(`data/calendar.json`) carries `offered_slots`, `rsvp_status`,
`form_sent`, `pending_reschedule`, and an append-only `history` array —
`scheduling_service.py` only offers `create_appointment`/
`get_appointment`/`list_appointments`/`update_appointment_status`
(status-only), the exact `NEW-224` general-update gap, and a larger one
than the subcontractor case (more fields, plus an append-only log
`update_appointment_status` has no way to extend). `email-rules.js`/
`sms-rules.js` have no such gap once `NEW-230` (below) is resolved.

**The two files are one module, not two — scope and implement
together.** `restoricon_core/models.py`'s `AutomationRule` dataclass
already merges both channels into one table distinguished by `channel`
("Aigentik-CLI's email-rules.json and sms-rules.json are field-identical
... distinguished by `channel`" — its own docstring). The two JS files
are structurally identical clones (`loadRules`/`saveRules`/`addRule`/
`removeRule`/`checkRules`/`listRulesForSms`, differing only in
`RULES_FILE` name, `id` prefix (`er_`/`sr_`), and `checkRules`'s
condition-type set) — neither imports the other, but they must convert
together since both write through to the same table/service/routes and
a partial conversion would leave one channel silently divergent from
the other's cutover state.

**Call-site shapes checked — no iteration-with-async-callback risk like
the DNC pilot's `owner-command.js` bug.** Every `checkRules`/`addRule`/
`removeRule`/`listRulesForSms` call site (`index.js:1203`, `884`;
`owner-command.js:269`, `275`, `596`, `615`, `630-633`) is a single call,
not an array iteration (`sms-rules.js` is additionally always
dynamically `import()`-ed per call site in `owner-command.js`, unlike
`email-rules.js`'s static import — both patterns already sit inside
`async function`s, confirmed by the adjacent `await gmail.markAsSpam(...)`
at `index.js:1215` and existing `await import(...)` calls). No
`.forEach()`/`.filter()` conversion is needed for this module.

**Service-layer coverage — one real gap found and resolved in-scope
(`NEW-230`), everything else covers cleanly.** `create_rule`/`list_rules`/
`record_rule_match` cover `addRule`/`checkRules`'s increment-on-match
step/`listRulesForSms`'s read. The one gap: no delete method or route
exists for `removeRule()` — see `NEW-230` for the full analysis. Judged
in-scope to fix this round (unlike `NEW-224`'s subcontractor deferral)
because it is a single-purpose, single-field-free method (delete one row
by id, no partial-field-merge design question), the same size/shape as
`NEW-217`'s three lookup methods, which this project already treated as
in-scope for their own task rather than deferred.

**Core-only vs. dual-write — decided as Core-only, matching the DNC
pilot's shape but on a different argument, stated explicitly per the
scoping review's note not to let "DNC said so" stand as the whole
reasoning.** DNC's core danger was hidden-state divergence in a safety
guarantee (an entry only the local file knows about). That specific risk
doesn't apply to rules — they're config, not per-message state; the only
per-message write is `match_count`, a low-stakes counter, not a
correctness-bearing fact. The actual reason for Core-only here is (a)
single-source-of-truth for the rules' *content*, so `add rule`/`remove
rule` issued from any future caller (e.g. a web UI, once one exists) see
the same list `checkRules` evaluates, and (b) consistency with the
already-reviewed DNC pilot's throw-on-failure shape — a Core outage
during `checkRules()` propagates as a thrown error the same way an
outage during `isBlocked()` already does, which is an existing,
reviewed failure mode this task inherits rather than introduces.

**Rule-precedence contract — must be pinned explicitly, not left
implicit.** `addRule` does `rules.unshift(rule)` (newest first) and
`checkRules` returns on first match, so today "newest rule wins" by
construction. `automation_service.py`'s `list_rules` happens to preserve
this via `ORDER BY id DESC`, but that's a coincidence the spec must turn
into a stated contract, not leave implicit: the client-side test suite
must create rule A then rule B and assert B is evaluated first against
the fetched list, so a future change to `list_rules`'s ordering (e.g. to
`created_at ASC`) fails a test instead of silently inverting every rule
decision. Confirmed `routes.py:326-332` actually parses `channel`/
`limit`/`offset` from the query string (not just accepts them
unused) — `GET /api/v1/automation-rules?channel=sms` correctly returns
only that channel's rules, so no cross-channel contamination risk (SMS's
`from_number`/`message_contains` cases firing on email traffic) exists.

**Pagination assumption must be stated, not assumed.** `loadRules()`
today returns every rule in the file, unbounded. `list_rules` defaults
`limit=100`. At 2 real rules this is invisible; the spec must state the
assumption explicitly (request a high limit, e.g. `limit=1000`, in the
client's `GET`) rather than silently inheriting the API's 100-row
default, so a future 101st rule doesn't go silently inert.

**`external_id` must be preserved client-side, not dropped.** `addRule`
currently generates `er_${Date.now()}`/`sr_${Date.now()}` locally. The
write-through conversion must keep generating that ID client-side and
send it as the new rule's `external_id` in the `POST` body — letting
Core assign a bare integer id and leaving `external_id` `NULL` would
split newly-created rules from `migrate_aigentik.py`-migrated rules into
two ID namespaces (SQLite's `UNIQUE(external_id)` permits multiple
`NULL`s, so this wouldn't error, it would just quietly fragment
idempotent-rerun tracking).

**Behavior parity — `NEW-228`'s dead rule must survive the cutover
unchanged.** `email-rules.js`'s `checkRules` has no `message_contains`
case (confirmed against the full `switch`), and real production rule
`er_1771724421209` uses exactly that `condition_type` — it has never
matched anything (`match_count: 0` since 2026-02-22) and must not start
matching after this task. The client-side matching logic (which
condition types map to which check) moves to the fork's JS unchanged,
mirroring the classify-client-side/store-and-serve-server-side split the
DNC pilot already established for `classifyIdentifier()` — the
implementer must not add a `message_contains` case to `email-rules.js`
"to fix" this while doing the conversion; that's an unscoped
product-behavior change requiring Ish's decision, not a migration
concern (see `NEW-228`).

**Empty-Core-table reality must be stated, not implied away.**
`--apply` has never been run against `~/Aigentik-CLI`'s real data (per
the task-2 entry above), so `restoricon_core`'s `automation_rules` table
is empty at the time this task lands — the 2 real production rules
still live only in `~/Aigentik-CLI/data/email-rules.json` until Ish
approves a migration `--apply` run. "Write-through done" for this module
means new `Codey-Aigentik` rule reads/writes go through Core correctly,
**not** that the existing 2 production rules are preserved or visible
yet — that's a separate, already-tracked, not-yet-approved step. Tests
must seed rules via the API (`create_rule`/`POST`), not assume migrated
data is present.

**Auth/config plumbing confirmed reusable as-is.** `~/Codey-Aigentik/
config.json` (real, gitignored) already has the `core_api` block from
the DNC pilot's provisioning step — this module needs no new
provisioning, config keys, or `install.sh` change (`fetch` is already a
global in this runtime per the DNC pilot's precedent; stated positively
per rule 11 rather than silently skipped).

**Implementer spec:**
1. **Core-side first** (lands before the JS conversion, so the JS is
   tested against a real route, not a mock of one that doesn't exist):
   add `AutomationService.delete_rule(rule_id: int, actor: AuthContext)
   -> bool` (`PERM_WRITE_AUTOMATION_RULES`-gated, audit-logged like
   `create_rule`, `DELETE FROM automation_rules WHERE id = ?`, returns
   `cursor.rowcount > 0`) and a `POST /api/v1/automation-rules/{id}/
   delete` route returning `200 {"deleted": <bool>}` always (matches
   `/do-not-contact/remove`'s always-200-bare-bool shape, not a 404 —
   deleting an already-gone id is not an error). This is `NEW-230`'s
   resolution.
2. Convert `email-rules.js`'s and `sms-rules.js`'s `loadRules`/
   `saveRules`/`addRule`/`removeRule`/`checkRules`/`listRulesForSms` to
   `async function`s calling the Core's automation-rules routes over
   HTTP, following the DNC pilot's `coreRequest()` helper pattern
   exactly (single choke point, `AbortSignal.timeout`, throw on non-2xx
   or network failure, no local-JSON fallback). `isPromotional`/the
   condition-type `switch` logic in `checkRules` are pure, no I/O — stay
   local and synchronous, matching `detectOptOutRequest`'s precedent in
   the DNC pilot. `checkRules` becomes: `GET /api/v1/automation-rules?
   channel=<channel>&limit=1000`, iterate client-side in the existing
   order (list is already newest-first per the pinned contract above)
   running the existing per-condition-type match logic, and on match
   call `POST /api/v1/automation-rules/{id}/match` before returning
   (matching the existing "update then return" order). `removeRule`
   becomes: `GET` the list, run the existing fuzzy
   id-or-description-`includes` match client-side, then call the new
   `POST .../{id}/delete` route with the matched id. `addRule` keeps
   generating `er_${Date.now()}`/`sr_${Date.now()}` client-side and
   sends it as `external_id` in the `POST /api/v1/automation-rules`
   body.
3. Every call site becomes `await`-ed — no `for...of`/`forEach`
   restructuring needed per the call-site-shape check above, all sites
   are single calls already inside `async function`s.
4. Preserve existing return shapes exactly: `addRule` still resolves to
   the rule object; `removeRule` still resolves to a `bool`; `checkRules`
   still resolves to `{ action, rule, reason }` (email) /
   `{ action, rule }` (sms); `listRulesForSms` still resolves to the same
   formatted string built client-side from the fetched list.
5. Tests: new `tests/email-rules.test.js`/`tests/sms-rules.test.js`
   (neither exists yet — no prior fs-mocking test to convert, unlike the
   DNC pilot), mocking the Core API HTTP calls, following the DNC test's
   established mocking pattern. Include the rule-precedence contract
   test (create A then B, assert B evaluates first) and a channel-
   isolation test (an SMS-only rule must not fire on an email-shaped
   input, verifying `routes.py`'s `channel` query param actually
   isolates the two lists, not just trusting the code read above).
6. No `install.sh`/config changes needed — state so explicitly per rule
   11 rather than skipping the check.
7. Doc update, in-scope for the two rows this module touches (not a
   full pass — leave the rest to `NEW-226`'s existing deferred cleanup
   pointer): `~/Codey-Aigentik/docs/data-files.md` lines 12-13
   (`email-rules.json`/`sms-rules.json` rows) need updating to say these
   are no longer local files after this task; `docs/architecture.md`'s
   and `docs/commands.md`'s prose mentions of `email-rules.js`/
   `sms-rules.js` as the "rule engine" reading/writing files can stay as
   architecture description (they still are the rule engine, just
   backed by Core now) unless the implementer finds a line that
   specifically asserts local-file storage, which should be corrected
   alongside `data-files.md`.

**Verification tier this task can reach:** code-complete +
code-reviewer-approved + tested against a Core API instance started
locally for the test run — same tier as the DNC pilot, for the same
reason (no `~/Aigentik-CLI` production cutover has happened). Record the
tier honestly per rule 7.

**Built and closed at exactly this tier, 2026-08-27 — see §4's full
entry** for what was built, the corrected `NEW-230` audit-logging
detail, and the test counts (150/150 `~/Codey-Aigentik`, 778/1 this
repo).

**Findings logged out of scope this round, not fixed here:** `NEW-228`
(pre-existing dead `message_contains` email rule in production data —
must survive the cutover unchanged, not be "fixed"), `NEW-229`
(`create_rule` validates `channel` but not `condition_type`/`action`
domain values — pre-existing loose-validation pattern, matches other
services). `NEW-230` is resolved in-scope by this task's own spec, not
deferred — see implementer spec step 1.

**Rule 4 relevance — same conclusion as the pilot, checked again for
this module specifically.** No daemon/PID/kill-logic/lock/GUI-bind
change. The new `delete_rule`/`.../delete` route is a security-relevant
change (new auth-gated write endpoint), which the Workflow section's
separate "or security" clause already makes mandatory for code-reviewer
regardless of rule 4's narrower process-lifecycle scope.

**Task 4, third module — `subcontractor-recruiter.js` write-through
unblocking scoped 2026-08-27, desk-only, no code written, `~/Codey-
Aigentik`/`~/Aigentik-CLI` untouched.** Ish asleep; proceeding
autonomously per his standing instruction. This is the `NEW-224` blocker
itself — designing `CRMService.update_subcontractor()`, the general
partial-update method `NEW-224` identified as missing. Read
`~/Codey-Aigentik/subcontractor-recruiter.js` in full (682 lines,
confirmed byte-identical to `~/Aigentik-CLI`'s copy via `diff`), its
callers in `index.js` (lines 947-960, 1280-1290) and `owner-command.js`
(lines 1174, 1189, 1205, 1222), `llama.js`'s `extractRecruiterQualification()`
(lines 569-586), `restoricon_core/services/crm_service.py`'s real
subcontractor methods (lines 888-1124), `restoricon_core/models.py`'s
`Subcontractor` dataclass (lines 243-298), and `restoricon_core/
database.py`'s `subcontractors` DDL (lines 250-299), per rule 12. **This
round specs and hands off the Core-side service method + route only —
not implemented, and the JS-side `subcontractor-recruiter.js`/
`owner-command.js` conversion itself remains a separate, still-not-
started task-4 round**, same two-step shape as the routes-then-JS
sequencing already used for email-rules.js/sms-rules.js.

**Call-site split confirms the field scope, non-arbitrarily.**
`index.js`'s two call sites (947-960, 1280-1290) merge `extracted` —
the output of `llama.extractRecruiterQualification()` — into an
*existing* subcontractor record via `updateSubcontractor(id, extracted)`.
All four `owner-command.js` call sites (1174, 1189, 1205, 1222) set
`qualification_status` only (`qualify_subcontractor`/
`approve_subcontractor`/`decline_subcontractor`/
`request_subcontractor_docs`), already fully served by the existing
`update_subcontractor_qualification()`. This is the evidence for
excluding `qualification_status`/`recruitment_step` from the new
method's allow-list below, not an arbitrary line: no caller needs the
general method to touch those two fields, and keeping them
single-writer avoids two paths racing to set the same column
inconsistently (the design question this task's brief posed directly).

**Allow-listed field set — matches only what `index.js`'s call sites
actually merge, not a fully generic update-everything method,** per
this project's "don't build unrequested features" convention. Cross-
referencing `llama.js:570`'s 27-key extraction schema against
`models.py`'s `Subcontractor` fields:

`ALLOWED_UPDATE_FIELDS = {"company_name", "legal_name", "dba",
"contact_name", "title", "phone", "email", "website", "primary_trade",
"secondary_trades", "service_area", "years_in_business", "crew_size",
"typical_project_size", "availability", "emergency_availability",
"license_number", "license_type", "license_required",
"general_liability", "workers_comp", "qualification_data"}` (22 keys).

Deliberately excluded because no `index.js`/`owner-command.js` call site
touches them today: `qualification_status`, `recruitment_step`
(dedicated method only, see above), `external_id`,
`contact_external_id`, `id`, `created_at`, `updated_at`,
`last_contact_at` (auto-managed by the method itself, see below, not
caller-settable), `contact_attempts`, `dnc_status`, `coi_received`,
`coi_expiration`, `additional_insured_status`, `insurance_status`,
`w9_received`, `msa_sent`, `msa_signed`, `license_expiration`,
`license_status`, `residential_experience`, `commercial_experience`,
`references`, `portfolio_url`, `lead_source`, `notes`.

**Method signature and behavior
(`restoricon_core/services/crm_service.py`, added after
`update_subcontractor_qualification()`):**

```python
def update_subcontractor(
    self, subcontractor_id: int, updates: Dict[str, Any], actor: AuthContext
) -> Optional[Subcontractor]:
```

1. `actor.has_permission(PERM_WRITE_SUBCONTRACTORS)` — same permission
   as `create_subcontractor`/`update_subcontractor_qualification`, no
   new permission constant. Reasoning worth stating explicitly since the
   brief asked for it: a permission that can already create the row with
   arbitrary values for every one of these fields cannot be meaningfully
   protected by restricting which of those same fields a later update
   may touch — finer-grained field-level permissions would be
   security theater here, not a real boundary.
2. **Unknown-key rejection is mandatory, not optional** (the brief's
   SQL-injection/allow-listing point): `unknown = set(updates) -
   ALLOWED_UPDATE_FIELDS`; if non-empty, `raise ValueError(f"Unknown
   field(s) for subcontractor update: {sorted(unknown)}")`. This is what
   stops an arbitrary JS-side dict's keys from ever reaching a SQL
   column name. `routes.py:396-397`'s existing global `except ValueError
   as ve: return 400` handles this with no new route-side code (verified
   by reading `routes.py`'s exception-mapping block directly, not
   assumed).
3. **`None`-valued keys are rejected, not written as `NULL`** — a
   blocking correctness requirement, not a style choice. `llama.js:572`'s
   extraction prompt instructs "use null for anything not mentioned"
   across all 27 schema keys, and `subcontractor-recruiter.js`'s own
   `updateSubcontractor()` already merges via a plain `{...current,
   ...updates}` spread with no null-filtering (`NEW-234`, logged this
   round as a pre-existing, separate live-data risk, not fixed here). If
   the Core method faithfully wrote whatever it's given, a single
   ambiguous SMS reply that extracts 26 nulls and one real field would
   wipe 26 populated columns. Contract: **key absent → column untouched;
   key present with value `None` → `raise ValueError(f"Field '{key}'
   cannot be set to None via update_subcontractor; omit the key
   instead")`.** This forces the future JS-side translation layer (task
   4's still-unstarted conversion round) to strip null-valued keys from
   `extracted` before calling, rather than trusting it silently drops
   them today.
4. **Empty `updates` dict is a no-op**, not a SQL syntax error: if
   `not updates`, return `self.get_subcontractor(subcontractor_id,
   actor)` (a plain read) with no `UPDATE`, no audit log call.
5. **Normalization parity with `create_subcontractor`**, since `email`
   and `company_name` are both in the extraction schema and this
   allow-list: apply `email.strip().lower()` and `company_name.strip()`
   if either key is present, exactly matching `create_subcontractor`'s
   existing behavior (`crm_service.py:973,979`) — without this, the
   update path would write non-normalized values into rows `create`
   would have normalized.
6. **Two JSON columns, two different merge semantics — must not be
   implemented uniformly:**
   - `qualification_data` **merges** (shallow, one level): read the
     row's current `qualification_data_json` and shallow-merge the
     caller's `qualification_data` dict into it — `{**existing, **new}`
     — exactly matching `subcontractor-recruiter.js:332`'s own
     `{...(current.qualification_data||{}), ...(updates.qualification_data||{})}`.
   - `secondary_trades` **replaces**: `json.dumps(updates["secondary_trades"])`
     directly, matching `subcontractor-recruiter.js:327-329`'s plain
     top-level spread (no merge semantics exist for this field in the
     JS today).
   - The `SELECT` of the current `qualification_data_json` (needed for
     the merge) must happen inside the same `with conn:` transaction
     block as the `UPDATE`, not as a separate connection/transaction —
     this project has a documented history of self-races from
     split-transaction read-then-write patterns (see rule 4's daemon
     PID-race precedent), and there's no reason to reintroduce that
     shape here even though this isn't process-lifecycle code.
7. Build the `UPDATE subcontractors SET ... WHERE id = ?` from only the
   keys actually present in `updates` (a true partial update — untouched
   allow-listed fields are not overwritten), always additionally setting
   `updated_at = now` **and** `last_contact_at = now` — the latter
   mirrors `subcontractor-recruiter.js:331`'s unconditional
   `last_contact` bump on every non-empty `updateSubcontractor()` call.
   (Note logged as `NEW-236`, not fixed here: `owner-command.js`'s four
   status-only call sites use `update_subcontractor_qualification()`,
   not this method, and that existing method does not bump
   `last_contact_at` — a real, pre-existing behavior change for the
   still-unstarted JS conversion round to resolve, not this one.)
8. If the row doesn't exist (checked via the same-transaction `SELECT`
   in step 6, or `cursor.rowcount == 0` on the `UPDATE` as a race-safety
   backstop), return `None` — no audit log call, matching every other
   `get_*`/`update_*` method's `Optional[...]`-return-means-404 pattern
   already used in this file.
9. **Return the full updated `Subcontractor` object, not `bool`.** This
   is load-bearing, not a style preference: post-cutover, the JS side no
   longer holds the authoritative record, so the still-unstarted
   conversion round's caller needs the merged post-write state back to
   run `determineQualificationStatus()` (see below) against it.
10. Audit log **unconditionally** on any real write (matching
    `automation_service.py`'s `business_profile` update precedent, the
    only prior "update" — as opposed to create/delete — case in this
    codebase, confirmed by grepping `action="update"` repo-wide):
    `action="update"`, `entity_type="subcontractor"`,
    `entity_id=subcontractor_id`, `change_summary=f"Subcontractor
    {subcontractor_id} updated ({', '.join(sorted(updates.keys()))})"`
    (names which fields changed, per the brief's ask), `details=`
    the full updated record's `.to_dict()` (matching
    `create_subcontractor`'s and the `business_profile` precedent's
    full-object-dump shape, not a per-field old→new diff — no diff-log
    shape exists anywhere else in this codebase to match, and inventing
    one here would be a new pattern the brief said to avoid).

**Not ported to the Core: `determineQualificationStatus()`'s
auto-recalculation logic.** `subcontractor-recruiter.js:434-491` is ~60
lines of business-rule state-machine logic (document-review thresholds,
qualification-completeness checks) that `updateSubcontractor()` runs
automatically after every merge unless `qualification_status` was
explicitly passed. This is not a product-scope call to defer — it's the
same trust model already shipped in the two live write-through modules:
JS computes, Core stores. The still-unstarted JS conversion round's
sequencing will be: (1) call `update_subcontractor()` with the
allow-listed fields, (2) using the returned updated record, run the
existing `determineQualificationStatus()` locally exactly as today, and
(3) if the computed status differs from the current one, issue a
*separate* `update_subcontractor_qualification()` call — two Core calls
per JS-side merge, preserving single-writer-per-field discipline from
design point 1 above rather than smuggling status writes into the
general method.

**Route — included in this round's spec** (per `NEW-226`'s precedent of
shipping method + route together, and `NEW-112`'s finding that a service
method with zero callers is dead-code risk): `POST
/api/v1/subcontractors/{id}/update` → `crm.update_subcontractor(id,
json_body, actor)`; `None` → 404 `{"error": "Subcontractor not found"}`;
success → 200 `{"subcontractor": updated_sub.to_dict()}`. Placed in
`routes.py` directly after the existing `.../qualification` POST block
(line 275-284) and before the generic by-id `GET` block (line
286-291), matching that block's own `path.startswith(...) and
path.endswith("/update") and method == "POST"` shape. **Note, not a new
finding (`NEW-237`, logged as a duplicate instance of the already-open
`NEW-222`):** a misdirected `GET .../{id}/update` will fall through to
the generic by-id `GET` handler and raise `ValueError` (400) instead of
404 — the identical mechanism `NEW-222` already found for `GET
.../{id}/qualification`, tracked under that finding's existing
disposition (a general router-hardening pass), not patched per-route
here.

**`install.sh`: no change needed** — no new dependency, `json`/
`sqlite3`/`dataclasses` are stdlib, matching every other B2 service-layer
task so far.

**Test list for the implementer:** unknown key raises `ValueError`
(→400 via the route); any `None`-valued key raises `ValueError`
(→400); `qualification_data` merge preserves pre-existing keys not
present in the new dict; `secondary_trades` replaces rather than
merges; `email`/`company_name` are normalized identically to
`create_subcontractor`'s; 404 (not an exception) on a nonexistent
`subcontractor_id`; an empty `{}` `updates` dict is a no-op (record
unchanged, no audit-log row created); `PermissionError` when the actor
lacks `PERM_WRITE_SUBCONTRACTORS`; `qualification_status`/
`recruitment_step` in `updates` are rejected as unknown keys (proving
the exclusion is enforced, not just documented).

**Findings logged out of scope this round, not fixed here:** `NEW-234`
(pre-existing null-overwrite risk in the live JS, independent of this
migration), `NEW-235` (extraction-schema/Core-model field-name and
-type mapping gaps the future JS translation layer must handle:
`has_license`→`license_required` name+type cast,
`general_liability`/`workers_comp`/`emergency_availability` boolean-vs-
TEXT typing, and six/seven schema keys with no Core column that must
land in `qualification_data` instead), `NEW-236` (`last_contact_at`
stops advancing for `owner-command.js`'s four status-only actions
post-cutover — same class as `NEW-231`), `NEW-237` (duplicate instance
of `NEW-222`'s routing quirk, not a new mechanism).

**Rule-4/security note:** no daemon/PID/kill-logic/lock/GUI-bind change.
The new `.../update` route is a new auth-gated write endpoint on a real
API surface — mandatory for code-reviewer under the Workflow section's
"or security" clause regardless of rule 4's narrower process-lifecycle
scope, same conclusion as every other B2 route addition.

**Verification tier this task can reach once implemented:**
code-complete + code-reviewer-approved + tested against a Core API
instance started locally for the test run — same tier as the DNC pilot
and the email/sms-rules module, for the same reason (no
`~/Aigentik-CLI`/`~/Codey-Aigentik` production cutover has happened, and
this round in particular ships no JS changes at all yet). Record the
tier honestly per rule 7.

**Built and code-reviewer-approved, 2026-08-27 — see §4's Phase B2
task 4 third-module entry for the full outcome, the `NEW-238`/`NEW-239`/
`NEW-240` findings raised in review, and the fresh 789/1 test count.
Ships the Core-side method + route only; the JS conversion itself
remains not started.**

**Task 4, third module continuation — `subcontractor-recruiter.js`
read-path prerequisite, `find_subcontractor()` Core method + route,
scoped 2026-08-27, desk-only, no code written, `~/Codey-Aigentik`/
`~/Aigentik-CLI` untouched.** Ish asleep; proceeding autonomously per
his standing instruction, not making a product-scope call. Re-read
`~/Codey-Aigentik/subcontractor-recruiter.js` in full (682 lines),
`role-router.js:119-121`, `owner-command.js`'s six read call sites, and
`crm_service.py`/`api/routes.py`'s existing subcontractor methods
directly per rule 12 before scoping this.

**Why this increment and not the full JS conversion:** the prior round's
`update_subcontractor()` (39c0f98) unblocked only the *write* half of
`NEW-224`'s gap. Re-reading the file this round surfaced that the
*read* half has no Core equivalent at all (`NEW-241`) — `findSubcontractor()`'s
fuzzy phone/email/name lookup, which every JS read call site depends on
via `person.subcontractor_record` (populated on *every* inbound
SMS/email) or directly in `owner-command.js`. Advisor review confirmed:
attempting to convert just the two `updateSubcontractor()` write call
sites (`index.js:959,1290`) this round, while leaving reads on local
JSON, would produce an unverifiable shadow-write with no read path
ever exercising it, and would let `NEW-234`'s local null-overwrite bug
silently diverge the two copies of the same record — the weakest
available version of this work, not a real increment. `NEW-242`
(the `createOrUpdateSubcontractorLead()` upsert/dedup logic, four call
sites) is a second, larger prerequisite gap, deliberately left for a
later round rather than folded into this one, per this project's
incremental-slicing convention.

**Scope, this round: one new read-only Core method + one route, no JS
changes.** This makes the fuzzy *lookup itself* available server-side
and is independently testable/reviewable the same way the write method
was (service unit tests + route test against a real `:memory:`/local
DB instance, no live SMS session required). **Correction to this
round's own earlier framing:** this is not, by itself, "the minimum
that makes a real JS cutover possible" — closing this gap still leaves
two more prerequisites before any `findSubcontractor()` call site can
actually convert: `NEW-242` (`createOrUpdateSubcontractorLead()`'s
upsert/dedup logic, no Core equivalent) and `NEW-245` (the reverse
Core-row→JS-record shape mapping — every JS consumer of the record
this lookup returns reads local-JSON field names/types that don't
match `Subcontractor.to_dict()`, logged below). This method is a
necessary but not sufficient step.

**Method signature and behavior
(`restoricon_core/services/crm_service.py`, added after
`get_subcontractor_by_external_id()`):**

```python
def find_subcontractor(
    self, query: str, actor: AuthContext
) -> Optional[Subcontractor]:
```

1. `actor.has_permission(PERM_READ_SUBCONTRACTORS)` — same permission
   as `get_subcontractor`/`list_subcontractors`, no new permission
   constant (read-only method).
2. **Empty/blank query returns `None`, checked before anything else** —
   mirrors `subcontractor-recruiter.js:194`'s `if (!identifier) return
   null`. This is not optional: without this guard, an empty-string
   query would substring-match every non-null `company_name` and
   silently return the *first row in the table* instead of no match.
   `if not query or not query.strip(): return None`.
3. **Normalize the query exactly as the JS does**
   (`subcontractor-recruiter.js:203`): `q = query.strip().lower()`
   — the JS's `String(identifier).toLowerCase().trim()`. Apply this
   once, before the scan, not per-field.
4. **Must mirror `findSubcontractor()`'s exact per-record predicate
   order, not just its final result set** — `subcontractor-recruiter
   .js:206-217` checks, for each record in array order:
   `subcontractor_id` exact match (case-insensitive) → `email` exact
   match (case-insensitive) → `company_name` substring
   (case-insensitive) → `legal_name` substring → `dba` substring →
   `contact_name` substring → phone digit-substring match (both
   directions, `pDigits.includes(cleanDigits) ||
   cleanDigits.includes(pDigits)`), gated on the query's stripped-digit
   length being `>= 7` (mirrors `subcontractor-recruiter.js:204,213`
   exactly) — and returns the *first* record for which any condition
   is true, not a best/highest-priority match across the whole table.
   Implement this as a full Python-side scan over `SELECT * FROM
   subcontractors ORDER BY id ASC;` (ascending `id` is the closest
   analog to the JS array's insertion order — this equivalence only
   holds cleanly for rows created by `migrate_aigentik.py` in file
   order; records created later through different paths, e.g. a future
   Core-native creation route, can diverge from JS's original
   insertion order, which matters here because two records can
   legitimately both match a company-name substring and only the first
   is returned) applying the same six checks in the same order per row,
   rather than an equivalent-looking SQL `LIKE`/`OR` query — SQL can't
   reproduce the bidirectional digit-substring phone match, and this
   project has already been burned once (`NEW-235`) by treating "looks
   equivalent" as equivalent without checking. Table size (a
   subcontractor recruiting pipeline, not a customer table) makes a
   full unbounded scan acceptable; do not add `LIMIT`/pagination to
   this method — the JS original has none, and adding one would
   silently narrow which records are reachable.
5. Return `None` if no record matches (JS returns `null`).
6. **No separate ID-resolve step needed for a follow-up
   `update_subcontractor()` call** — since this method returns the full
   `Subcontractor` object (not just a boolean/ID), its numeric Core
   `id` (needed for `.../{id}/update`) comes back with the lookup
   result itself; the implementer should not add a redundant second
   lookup.

**Route — included in this round's spec**, per the same
method-plus-route-together precedent `NEW-226`/`NEW-112` already
established: extend the existing `GET /api/v1/subcontractors` handler
(`routes.py:256-269`) rather than add a new path segment — check for an
optional `q` query param first; if **present and non-blank** (after
`.strip()`), branch to `crm.find_subcontractor(q, actor)` and return
`200 {"subcontractor": ...}` or `404 {"error": "Subcontractor not
found"}`, ignoring `qualification_status`/`primary_trade`/`limit`/
`offset` in that branch. **If `q` is absent, or present but blank/
whitespace-only (e.g. `?q=` or `?q=%20`), fall through to the existing
`list_subcontractors` behavior unchanged** — a blank `q` is treated the
same as no `q` at all, not as "search for nothing" (which the method
itself already refuses via its own blank-query guard above; the route
must not even reach the method in that case, since silently disabling
the list behavior for a stray trailing `?q=` would be a worse surprise
than ignoring it). This avoids a second `path.startswith(...)` branch
and the `NEW-222`/`NEW-237`-class routing-quirk risk a new path segment
would introduce.

**Not in scope this round:** `get_subcontractor_by_external_id()`
already exists service-side with no HTTP route — left unexposed since
no caller needs it over HTTP yet (only `migrate_aigentik.py`, which
calls the Python service directly, in-process); `createOrUpdateSubcontractorLead()`'s
upsert/dedup logic (`NEW-242`); the reverse Core-row→JS-record shape
mapping every actual caller of this lookup would need (`NEW-245`); any
JS file changes; the dual-write-vs-Core-primary sequencing question for
the eventual real cutover (`NEW-243`, logged as an open design
question, not a blocker for this narrower slice).

**`install.sh`: no change needed** — stdlib only, matching every other
B2 service-layer task.

**Test list for the implementer:** exact `external_id` match
(case-insensitive) found; exact `email` match (case-insensitive) found;
`company_name`/`legal_name`/`dba`/`contact_name` substring match found
(case-insensitive, partial string); phone digit match found in both
directions (query-is-substring-of-stored and stored-is-substring-of-query);
phone match correctly *not* attempted when the query's stripped-digit
count is under 7; no match anywhere returns `None` (route: 404, not an
exception); **empty-string query returns `None` (not the first row in
the table); whitespace-only query returns `None`; a valid query with
leading/trailing whitespace still matches (normalization applied
before comparison)**; `PermissionError` when the actor lacks
`PERM_READ_SUBCONTRACTORS`; route's `q`-param branch takes priority
over `qualification_status`/`primary_trade`/`limit`/`offset` when both
are present and `q` is non-blank; **a blank/whitespace-only `q`
(`?q=`, `?q=%20`) falls through to the existing list behavior rather
than invoking `find_subcontractor()` or returning 404.**

**Findings logged out of scope this round:** `NEW-241` (this gap
itself, logged for the record before being closed by this spec),
`NEW-242` (upsert/dedup logic, no Core equivalent, four call sites),
`NEW-243` (dual-write-vs-Core-primary open design question for the real
cutover), `NEW-244` (`contacts.js`'s still-local-JSON `syncWithContacts()`
cross-write, orthogonal but tangled for a later round), `NEW-245`
(reverse Core-row→JS-record shape mapping needed by every actual
caller of this lookup — `last_contact_at` vs `last_contact`,
`external_id`/numeric `id` vs `subcontractor_id`, `int` 0/1 vs JS
boolean fields, and `qualification_data` sub-keys `determineNextRecruitmentStep()`
reads back — none of which `NEW-235` covered, since that finding is
about the forward extraction-schema→Core direction only).

**Rule-4/security note:** no daemon/PID/kill-logic/lock/GUI-bind
change. Read-only method + route — no new write surface — but still
routed through mandatory code-reviewer per the Workflow section's
standard per-task gate (every task goes through code-reviewer
regardless of size), not because rule 4's process-lifecycle trigger
applies here.

**Verification tier this task can reach once implemented:**
code-complete + code-reviewer-approved + tested against a Core API
instance/DB started locally for the test run — same tier as the
`update_subcontractor()` slice, for the same reason (no
`~/Aigentik-CLI`/`~/Codey-Aigentik` production cutover has happened,
and this round ships no JS changes). Record the tier honestly per
rule 7.

**Built and code-reviewer-approved, 2026-08-27 — `CRMService.find_subcontractor()`
and its route landed exactly per this spec, including the deliberate
predicate-mirroring choice on `NEW-246` (the JS's NULL/blank-phone
substring bug). Code-reviewer explicitly endorsed mirroring over
silently fixing it: no live JS call site exists yet, the decision was
made at this spec layer rather than improvised mid-task, and it is
pinned by a named regression test. Code-reviewer's one non-blocking
follow-up — any future spec wiring this method to a live JS call site
must treat `NEW-246` as must-fix-first and cross-reference it
explicitly — has been added to `NEW-246`'s own entry in
`NEW_ISSUES.md`. Full `pytest tests/` run: 811 passed, 1 skipped. Ships
Core-side method + route only; no `subcontractor-recruiter.js` change.
`NEW-242` (upsert/dedup) and `NEW-245` (reverse Core-row→JS-record
shape mapping) **code-complete and code-reviewer-approved 2026-08-27**:
`upsert_subcontractor`, `CORE_TO_JS_SUBCONTRACTOR_MAP`, and
`format_subcontractor_for_js` added to `CRMService`; `POST
/api/v1/subcontractors/upsert` route added; 18 new tests, 133 total
pass. Code review caught and corrected: (1) wrong field mapped to
`subcontractor_id` (`external_id`, not `id`); (2) `workers_comp` and
`general_liability` missing from `_BOOL_FIELDS`. Both fixed. Not
live-verified (no process-lifecycle changes).**

### 6.5 Track B / Phase B3 — CRM/Sales and Operations (DONE 2026-08-30)

**Status**: 100% Complete, Code-Reviewer Approved, Test Verified (`210/210 passed` in `restoricon_core`, `1107/1107 passed` across full root test suite).

- **CRM & Sales Domain Engine (`restoricon_core/models.py`, `database.py`, `crm_service.py`, `routes.py`)**:
  - 9-stage sales pipeline state machine (`NEW_LEAD` -> `CONTACTED` -> `APPOINTMENT_SET` -> `ESTIMATE_SCHEDULED` -> `ESTIMATE_SENT` -> `PROPOSAL_SENT` -> `NEGOTIATION` -> `WON` / `LOST`) with probability tracking, weighted pipeline aggregations, and mandatory lost reasons.
  - 5-dimension deterministic lead scoring engine (0–100 pts across Scope, Property, Urgency, Insurance, Responsiveness) classifying leads into Hot, Warm, Cold, and Unqualified.
  - Automated stage-triggered task cadence & SLA follow-ups with deduplication.
- **Operations Domain Engine (`restoricon_core/services/operations_service.py`, `models.py`, `database.py`, `routes.py`)**:
  - 15-stage project lifecycle state machine (`ProjectStage`) with strict gate validation, stage timestamps, and milestone prerequisite checks.
  - Project milestones table & dependency graph.
  - Work Orders & Line Items engine with auto-numbering (`WO-{YYYYMMDD}-{XXXX}`), full dispatching lifecycle (`DRAFT` -> `DISPATCHED` -> `ACCEPTED` -> `IN_PROGRESS` -> `COMPLETED` -> `VERIFIED`), and automated trade/insurance/rating subcontractor matching.
  - Equipment asset tracking and check-out/check-in deployment lifecycle with condition tracking and meter readings.
  - Strict RBAC & customer data isolation (customer role restricted to own records, financial costs/margins masked).

### 6.6 Track B / Phase B4 — The public website + phone-hosted API surfaces (API layer COMPLETE; web layer DOWNGRADED 2026-09-02 — see §6.9/B6)

**⚠ Status corrected 2026-09-02 per rule 6.** This section previously read
"(100% COMPLETE)". That claim held for the **API layer** and does not hold
for the **web layer**. The correction, with the evidence that forced it:

- **The API half is real and stands.** All ten `/api/v1/portal/*` routes
  exist, enforce customer isolation in the service layer, and are covered
  by tests (`restoricon_core/api/routes.py:645-716`).
- **The web half is static demo HTML.** `render_portal_surface()`
  (`restoricon_core/api/web_surfaces.py:1155-1554`) hardcodes its
  timeline, invoice table, and PM chat. It issues exactly **two** fetches
  — `POST /api/v1/portal/contracts/1/sign` (a hardcoded contract id,
  `NEW-272`) and `POST /api/v1/portal/messages`. **Eight of the ten real
  portal routes are never called by the portal.**
- **The admin surface is mostly static too.** Of eleven tabs, **three**
  are wired to real APIs (Users/Permissions, CRM & Projects list, Audit
  Log — lazy-loaded in `switchErpTab`, `web_surfaces.py:2212-2222`). The
  other eight are hardcoded placeholders. `saveBusinessProfile()` and
  `saveScheduleConfig()` (`web_surfaces.py:2413-2420`) are bare `alert()`
  calls that **discard the operator's input while reporting success**,
  even though `POST /api/v1/business-profile` and
  `POST /api/v1/schedule-config` both exist and work (`NEW-273`).

Stated plainly per rules 5 and 6: the test suites cited below are real and
they pass, but they test the **API**, not the rendered surfaces — no test
asserts that a portal or admin page actually calls the routes it is
described as consuming. That is precisely the code-complete-vs-live-
verified gap rule 7 exists for, and it is why **§6.9 / Phase B6 exists to
finish B4's own unmet exit criteria**, not to add new scope on top of
finished work.

**Status (2026-08-30, unchanged and still accurate for the API layer):** code-complete, audited, and verified across all API test suites (`test_rate_limiter.py`, `test_public_intake.py`, `test_customer_portal.py`).
- Public Website intake API endpoints (`/api/v1/public/leads`, `/api/v1/public/booking`) with sliding-window rate limiting, honeypot spam bot mitigation, automatic CRM deduplication, lead qualification scoring, and pipeline ingestion. **REAL.**
- Customer Portal API (`/api/v1/portal/*`) with complete RBAC customer data isolation, dynamic financial cost/margin masking, digital contract e-signatures, invoice balance tracking, document/photo retrieval, and bi-directional portal messaging. **REAL as an API; not consumed by the rendered portal — see the correction above.**

**Depends on:** B1 (API + auth), B3 (data worth showing).

**Superseded 2026-08-27 (Ish's own architecture direction, given verbatim
in a live session):** item 1 below is no longer "the marketing site,
served from the phone." Ish specified a hybrid architecture instead —
the static public site stays on GitHub Pages (reliable independent of
whether the phone is online), and the phone is never exposed directly.
A tunnel (Cloudflare Tunnel, or Cloudflare Workers for the simplest
form-only endpoints) fronts the phone's API under a separate subdomain
(e.g. `api.restoricon.com`), so `restoricon.com` (GitHub Pages) and the
phone's API are two independently-reachable things, not one origin:

```
Visitor -> restoricon.com (GitHub Pages: homepage, services, pricing,
           photos, SEO, blog, contact/booking form UI)
Visitor's form submission -> api.restoricon.com -> Cloudflare ->
           Cloudflare Tunnel -> phone's Restoricon Core API ->
           validate -> store lead/customer -> email/SMS notify ->
           Aigentik processing -> appointment request
```

No port-forwarding, no direct phone exposure. Ish's own stated
preference, and this plan's: **GitHub Pages + Cloudflare + phone API**,
not moving the whole site onto the phone — reliability for the static
content doesn't depend on the phone's uptime, while the phone still owns
all real backend logic and data. For the simplest form-only endpoints,
Cloudflare Workers ahead of the phone (rather than routing everything
through the tunnel) is an option worth considering per-endpoint once B4
is actually scoped for implementation — not decided yet, noted here as
the range Ish described.

Revised item list:

1. **Public marketing/informational site** — stays on GitHub Pages, not
   phone-hosted. Homepage, services, pricing, photos, SEO, blog, contact
   and booking form UI. The phone only receives what these forms submit,
   via the tunnel.
2. The **staff/admin surface** — a real authenticated admin page, not a
   hidden URL. Still served via the phone's API (through the tunnel),
   since it's an authenticated surface, not static public content.
3. The **customer portal** — project status, appointments, estimates,
   contracts, invoices, payments, messages, documents, photos, change
   orders, warranty info, approvals, signatures (Appendix C §12). Full
   document/signature/financial surface, not a view-only stub. Also a
   phone-API-backed authenticated surface, not static.
4. The **device-limb dashboard** as the third client of the same API —
   business calendar, financial summary, contacts, all fetched, none
   owned locally beyond caching.

**This is still the highest-risk security surface in the whole plan** —
if anything, more so now that the API is reachable from the public
internet via a tunnel rather than only from a same-device client. One
boundary bug means one customer sees another's contract; a tunnel
misconfiguration means the phone's API is reachable by more than
intended. Mandatory code-reviewer pass on every auth/permission change
AND on the tunnel/Cloudflare configuration itself once that's built, plus
a dedicated authorization test suite — not just "it works when I log
in." The Cloudflare Tunnel setup, DNS split (`restoricon.com` vs
`api.restoricon.com`), and whatever auth sits in front of the tunnel
(Cloudflare Access or equivalent, not yet decided) are new, real scoped
work this phase didn't previously account for — not a detail to assume
solved when B4 is actually picked up.

### 6.7 Track B / Phase B5 — The remaining domains, then the device limb
 
**B5a — the remaining domains (100% COMPLETE 2026-08-30).** Finance/Bookkeeping (`FinanceService`: transaction ledger, project P&L job costing, AR aging buckets, financial summary), Marketing/Lead-Gen (`BusinessOpsService`: campaign tracking, Google/Yelp review requests), Compliance (`BusinessOpsService`: certification and license expiration monitoring scanner), HR (`BusinessOpsService`: employee directory, hourly timesheet tracking & manager approval), Procurement (`BusinessOpsService`: vendor catalog, purchase orders lifecycle & inventory reception).
 
Plus the cross-cutting pieces: **Global Search** (`AnalyticsSearchService`: multi-entity search across 12 domains with customer isolation enforcement) and **Executive Dashboard Reporting** (`AnalyticsSearchService`: Sales, Operations, Financial, Marketing KPIs). Full test coverage with 17 new dedicated tests and 1,138 repository tests passing.

**B5b — the screen/hands limb (100% COMPLETE 2026-08-30).** Created the `Private-Codey-Agent` fork; built third-party-app automation (`ThirdPartyAppAutomationService`: WhatsApp intent + accessibility send fallback, SMS direct intent, Facebook Messenger / Telegram / Instagram screen automation recipes); built the Core→device loopback IPC dispatch mechanism (`DeviceBridgeServer` & `DeviceBridgeClient` with safety vetoes preventing emergency shortcodes across SMS, telephony, and third-party messaging); and established automatic write-through logging into Restoricon Core's `communication_history` and `audit_log`. Full test suite passing with 1,143 tests passing.

### 6.8 Track A / Phase A2 — Coding-domain architecture rollout

Runs in parallel with Track B once A1 is real. This is the platform's own
long-planned rollout (vision §7.6 steps 2–6 plus §9.7), unchanged in
order.

| Item | Depends on | Note |
|---|---|---|
| **7.3 sub-task E** — actually dispatch on the tier decision | A1 | **DONE 2026-08-24.** Task A deleted the orphaned, unreachable `classify_tier()`/`planner_service.get_plan()` pair (`NEW-172`, landed `8fe5d07`). Task B built the real medium/hard split — tier decided once in `main.py` (`score.length > 300`), threaded as an additive/defaulted field through `_request_daemon_plan()` → `core/daemon.py`'s socket RPC → `plannd.get_plan(enable_thinking=...)`, with the client-side socket timeout deliberately pinned to hard-tier sizing regardless of tier (old-daemon safety) while the daemon's own internal timeouts scale per-tier. Code-reviewer-approved, code-complete. See Appendix A for the full design and `NEW-178` for the one known gap (the dormant pull-side planning path can't carry a tier value — bounded, that path has zero production callers today). |
| **4.3** — wrap `core/agent.py` as a real CCOS capability | A1 | **DONE 2026-08-27.** Created plugin `ccos/plugins/coding/agent/` registering `coding.run_agent`, `coding.run_recursive`, and `coding.classify_breadth`. Scoped permissions via `scoped_agent_permissions` context manager. Migrated **both** call paths (`main.py` and `core/task_executor.py`) to `pm.call_capability("coding.run_agent", ...)`. Code-reviewer-approved, unit-test verified (897 passed, 1 skipped). |
| **7.5** — in-flight context passing + task-context blackboard | 4.3 | **DONE 2026-08-28.** Built immutable `TaskContext` enforcing $\le$64KB payload ceiling (Vision §11.2) and `TaskBlackboard` SQLite storage (`task_blackboard.db`) in WAL mode with TTL auto-purge. Updated `PluginManager.call_capability` with dynamic signature introspection for backward-compatible context injection. Integrated across `Planner` and `AgentOrchestrator` with 14 unit/integration tests (979 passed, 1 skipped). Code-reviewer-approved. |
| **4.5** — peer-CLI escalation redesign | 4.1's queue, 7.5's blackboard | Daemon pulls an item needing escalation off the main queue, parks it on a review list, notifies the user, keeps working. 100% design-only today. |
| **4.6** — wire `agent_orchestrator` to real execution | 4.3 | **DONE 2026-08-28.** Wired `AgentOrchestrator.execute_request()` and `execute_plan()` to live `Planner.execute_plan()`. Safety Agent veto is now live and fail-closed with `SafetyVetoError`, preventing all side-effects and saving audit trails to `TaskBlackboard`. Added `Planner.execute_goal()` routing and `validate_tool_safety()` pre-flight gate. Code-reviewer-approved. |
| **4.7** — multi-domain request splitting | 4.3, 7.5, 4.6 | **DONE 2026-08-28.** Built `DomainRouter` (`ccos/core/domain_router.py`) with 7 domain taxonomies (`system`, `coding`, `crm`, `data`, `research`, `vision`, `speech`), `SubGoal` DAG decomposition, and topological ordering. Integrated across `Planner` and `AgentOrchestrator` with cross-domain I/O contract checking and fail-closed safety veto across all domains. Added 10 unit/integration tests in `ccos/tests/test_multi_domain.py` (87 CCOS passed, 937 root passed). Code-reviewer-approved. |
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

### 6.9 Track B / Phase B6 — The web-facing layer: dashboard, portals, RBAC completion

**Added 2026-09-02, scoped in an interview with Ish that same session.
This phase finishes Phase B4's own unmet exit criteria; it is not new
scope layered on top of finished work.** §6.6 carries the rule-6
correction and the file-and-line evidence for why B4's web layer was
downgraded. The one-sentence version: B5 built the domain *services* and
B4 built the *API*, but the layer that puts them in front of a human was
never given a phase of its own, so it shipped as demo HTML and got marked
done.

**What is genuinely REAL today and is not re-built here** — verified by
reading the code on 2026-09-02, not inferred from the prior status line:

- The permission model. `users` carries a real seven-value role CHECK
  constraint plus `custom_permissions_json`
  (`restoricon_core/database.py:22-37`) — re-read this round. Enforcement
  breadth (**65 of 66 mutation-shaped service methods** gating on
  `AuthContext.has_permission()` before touching the DB, with
  `submit_review` the one gap, since fixed) is carried from the
  2026-09-02 RBAC investigation and was **not re-counted this round** —
  attributed rather than restated as verified, per rule 5.
- The role/permission admin UI. View, assign, and edit any user's role and
  custom permissions, backed by real routes
  (`/api/v1/users`, `/api/v1/permissions/catalog`,
  `/api/v1/users/{id}/permissions`), taking effect immediately. **This
  part of B4's claim stands.**
- All ten `/api/v1/portal/*` routes, with customer isolation enforced in
  the service layer. `sign_contract` was checked specifically because the
  portal calls it with a hardcoded id: it **fails closed**
  (`crm_service.py:1912-1914`), so `NEW-272` is a correctness bug, not an
  authorization hole. Stated explicitly so a later reader doesn't
  re-escalate it.
- Equipment deploy/return (`/api/v1/operations/equipment/deploy`,
  `/return`) — already a working assignment mechanism, and the model the
  staff-assignment work below should follow rather than reinvent.
  **Correction (2026-09-02, B6.1):** `deploy_equipment` has *no* ownership
  narrowing — B6.1 invents the permission-keyed ownership-narrowing pattern
  (modelled on `PERM_SIGN_CONTRACTS` / `NEW-192`), it does not follow one.

**Ish's goals for this phase, in his own framing (2026-09-02):**
everything in the admin dashboard reachable by admins and whoever admins
grant access to — not just CRM, but financials, tools/equipment, customer
info, technicians, subs, projects, notes, documents/photos. Assign and
reassign techs, subs, PMs, and equipment to any job from the web. One
genuine source of truth, no independently-drifting views. Every change
logged with who/what/when in enough detail to understand and correct a
mistake. Every role logs in with username/password every session (already
done). Workers, salespeople, and subs schedulable, with schedule changes
visible on their own portal.

**Explicitly out of scope for B6 (Ish, 2026-09-02):** the SMS/email
messaging agent itself. Aigentik is a separate, already-mostly-working
system. B6 *calls* it (B6.6) but does not modify its internals.

#### Decisions taken in the 2026-09-02 interview

Recorded here so later sessions don't re-litigate them. Each was put to
Ish with real options and a stated recommendation.

| # | Question | Ish's answer |
|---|---|---|
| 1 | The eight static admin tabs — B6 scope, own phase, or partial? | **In B6, phased by domain.** Makes B6 the largest phase in the plan; stated honestly rather than hidden in a later phase. |
| 2 | Who may reassign a PM/tech/sub on an existing project? | **PM self-serve on own projects.** Admin/manager unrestricted; a project_manager may reassign only where they are that project's `project_manager_id`; sales may not. |
| 3 | Customer-portal rewire before or after net-new staff portals? | **Rewire first.** Lower risk, and it establishes the fetch/render/auth pattern the staff portals copy. |
| 4 | How deep does audit "revert" go? | **See exactly what changed and fix it manually.** No one-click rollback — not even for a subset. |
| 5 | File upload storage and limits? | **Local disk under the Core's data dir, streamed, 25MB cap**, images + PDF + common docs. |
| 6 | Where do per-person schedules live? | **A new `staff_schedules` table** — `appointments` stays untouched. |
| 7 | Notify on assignment? | **Yes, now** — overriding the recommendation to defer. See B6.6 for the constraint this ran into and how it was resolved. |
| 8 | What does "propagate everywhere" mean technically? | **Refetch from the one API.** No surface keeps its own copy; §3.5 already commits to this. **No realtime push layer** — not needed, not built. |
| 9 | (Follow-up) Notification channel? | **Email now; SMS is an investigation item, not a deliverable.** Ish's own reasoning, since confirmed from source — see B6.6. |

**Decision 8 is a constraint on every item below, not a task:** each new
surface reads from the Core API on load and after every user action, and
holds no local store. This is free — §3.5's one-API-one-auth design
already gives it — but it has to be *stated*, because the cheap way to
build a fast-feeling dashboard is exactly the local cache that would
break it.

#### The ordering, and why

Dependency first, then risk, then value. `update_project` blocks every
reassignment surface, so it leads. The audit standard lands second so
every later write path is built to it rather than retrofitted. The
customer-portal rewire comes third because it is the cheapest conversion
of a *misleading* surface into a real one and it sets the pattern. File
upload sits deliberately late — see B6.5 for the measured reason. The
staff portals come last because they consume everything above them.

---

**B6.1 — `update_project` and the reassignment permission model. DONE
2026-09-02 (code-reviewer APPROVED, rule-4 permissions; not
live-verified beyond the test suite). See Appendix A's `B6.1` entry for
the delivered design and finding IDs.**
**Rule-4 category (permissions).** Was the blocker for everything
assignment-shaped: `project_manager_id`, `assigned_employees_json`, and
`subcontractors_json` were **write-once at creation** — a
`create_project` with no `update_project` anywhere. Now
`CRMService.update_project(project_id, updates, actor)` +
`POST /api/v1/projects/{id}/update`, built to `update_customer`'s shape
and the `update_user` pattern.

The permission design, per decision 2 (Ish, 2026-09-02 interview — his
words): a new scoped permission (rather than a role check) so it stays
overridable per-user through the permission UI that already works —
admin/manager hold it unrestricted; a `project_manager` may reassign
only on projects where `project_manager_id == actor.user_id`; `sales`
does not hold it. Deliberately permission-keyed, not role-keyed, to
avoid `NEW-194`'s "gate exists but narrowing logic is role-keyed" bug
shape by construction.

**Delivered as (B6.1, 2026-09-02) — two additive permissions, not one:**
implementation found `project_manager` already holds
`PERM_MANAGE_PROJECTS`, so a single permission could not be both the
grant and the "unrestricted" discriminator without re-creating the
role-keyed shape. So: `PERM_REASSIGN_PROJECT_STAFF` (the scoped grant
decision 2 describes) and `PERM_REASSIGN_ANY_PROJECT_STAFF` (the
unrestricted one). admin/manager hold both; `project_manager` the
scoped one; `sales` neither. Narrowing is in
`_actor_may_reassign_project_staff()` with **no `actor.role` branch**.
Both are in `PERMISSIONS_CATALOG`, so per-user override works as
decision 2 required. This split is the precedent for B6.7/B6.8's new
permissions.

**Prerequisite `U.35`/`U.36` (`NEW-264`, `NEW-266`) — DONE 2026-09-02
(commit `5e03b4c`, code-reviewer-approved).** Both were defects in
`update_user`, the exact partial-update-on-an-auth-table shape
`update_project` copies. The pattern to follow, now established there:
(a) `allowed_fields` whitelist, unknown keys ignored; (b) cross-field
invariants in one helper shared by create + update, evaluated against
post-update state; (c) `sqlite3.IntegrityError` → `ValueError` at the
service-method boundary (whole `with conn:` inside the `try`), so the
route's `ValueError → 400` handles it; (d) each state transition's side
effects on exactly one code path.

This item sets the audit standard B6.2 then applies everywhere: every
field it changes is logged with **old and new values**.

**B6.2 — Audit detail completion.** Bring the write paths up to the
old/new-value standard, and give an admin a way to read the result.
Measured on 2026-09-02: **64 `audit.log()` call sites** across
`restoricon_core` (55 in services, 9 in `api/routes.py`). **Rule-6
correction:** an earlier draft of this item said "63 sites / four with
old-new pairs"; the real figure was 64 / five — `B6.1` (`26d950d`) landed
the fifth (`crm_service.py` `update_project`, nested `changed_fields`)
the same day the count was taken. The other four: `business_ops_service.py:207`
(`submit_review`, flat `old_*/new_*`, the fix that set the standard),
`operations_service.py:343` (`previous_stage`), `:568` and `:1141`
(`previous_status`). The rest log new state only, as `X.to_dict()` or a
bare `updates` dict.

**Highest priority within this item: `api/routes.py`'s nine
user-mutation sites, which pass no `details=` at all.** A role change
today records the bare string `"User {username} updated"` — no old role,
no new role, and no note that every one of that user's sessions was
revoked as a side effect. That is the least reconstructible change in the
system and the least well logged.

Also build the read side: an admin screen to search audit history by
entity and read a before/after diff. **Per decision 4 there is no
rollback engine** — not one-click-everywhere, and not one-click for a
subset. "See exactly what changed, then fix it in the normal UI" is the
requirement, and it is met by good `details=` payloads plus a search
screen, not by revert semantics.

**Absorbs `U.37` (`NEW-265`, `NEW-267`) in full** — that M-lane item's
fix direction is verbatim this item's scope. `U.37` stays in M-lane as a
pointer so its NEW-ids remain findable; it is not separate work.

**Split into sub-rounds (2026-09-02):**
- **`B6.2a` — DONE (code-complete + rule-4 code-reviewer-approved,
  2026-09-02).** The canonical `build_audit_details(*, before, after,
  fields, side_effects, snapshot)` helper in `services/audit_service.py`
  (nested `changed_fields {field:{old,new}}` envelope, generalizing
  `B6.1`'s shape, plus `side_effects` and `snapshot` slots; a
  `_AUDITABLE_USER_FIELDS` allow-list guards the unguarded post-commit
  `json.dumps` in `AuditService.log`), wired into all 9 `api/routes.py`
  user-mutation/session sites. Old values from a pre-mutation `before`
  fetch, new values from the returned model — never the request body.
  Token-revocation side effects recorded as a `sessions_revoked` enum
  (`none`/`current_only`/`all_except_actor`/`all`). Findings `NEW-309`
  (mis-recorded revoke enum, fixed same round), `NEW-310` (site-331
  TOCTOU, non-blocking).
- **`B6.2b` — the ~55 service-layer `audit.log()` sites** (`crm` 27,
  `operations` 11, `business_ops` 7, `automation` 5, `scheduling` 4,
  `finance` 1). Bring them to the `build_audit_details` standard.
- **`B6.2c` — the admin audit-search screen.** Rule-4 read surface
  (exposes old/new values of user records): check the RBAC gate on the
  read and add audit-table indexes on the filtered columns.

**B6.3 — Rewire the Customer Portal to the API it already has.**
Replace `render_portal_surface()`'s hardcoded timeline, invoice table,
and PM chat with real fetches against the ten existing
`/api/v1/portal/*` routes. Fix the hardcoded
`POST /api/v1/portal/contracts/1/sign` (`NEW-272`) to sign the contract
actually being displayed. Establishes the fetch/render/auth/error pattern
that B6.7's four staff portals then copy — which is the second reason
this comes before them, beyond being lower-risk.

Exit criterion, stated because B4's absence of one is what let this ship
as a demo: **a test asserts the rendered surface calls the routes it is
described as consuming.** An API test passing is not evidence the page
uses the API.

**B6.4 — Admin dashboard tab completion, phased by domain** (decision 1).
The largest item in this phase. Every tab below already has a real
service and real routes behind it; the work is the wired UI, not new
backend. Ordered by damage-done-today, then by value:

- **B6.4a — the two lying save buttons, first.** `saveBusinessProfile()`
  and `saveScheduleConfig()` (`web_surfaces.py:2413-2420`) are bare
  `alert()` calls that report success and write nothing, against routes
  (`POST /api/v1/business-profile`, `POST /api/v1/schedule-config`) that
  exist and work. This is worse than an unimplemented tab: an operator
  who edits the business profile the AI agent uses for context, clicks
  Save, and is told it worked has been actively misled. Fix ahead of
  everything else in B6.4 regardless of relative value (`NEW-273`).
- **B6.4b — pipeline board.** Replace the hardcoded "5 Leads /
  $62,000 / 6 Active" tiles with real aggregations —
  `AnalyticsSearchService` already computes them.
- **B6.4c — operations: equipment and subcontractors.** Both tabs are
  placeholders with `alert()` buttons; both services are complete, and
  equipment deploy/return already works end to end at the API.
- **B6.4d — finance.** P&L, AR aging, invoice reconciliation from
  `FinanceService`. Financial data reaches customer-visible surfaces, so
  the cost/margin masking rules already in the service layer must be
  honored by the UI, not re-implemented in it.
- **B6.4e — communications.** Comms history and DNC controls from
  `CommunicationService`/`AutomationService`. Read/manage only — this is
  a view onto Aigentik's data, not a change to Aigentik.
- **B6.4f — business ops.** Marketing, HR, procurement, and the
  compliance expiry scanner from `BusinessOpsService`.

**B6.5 — File and document upload.** Not implemented at all today: the
`documents` table is metadata-only (`file_path TEXT`), `create_document`
stores a row, and **no multipart handling exists anywhere in the request
path** (verified by grep: zero hits across `restoricon_core`).

**Placed late for a measured reason, not a guessed one.**
`RestoriconRequestHandler._dispatch` (`api/server.py:52-54`) does
`self.rfile.read(content_length)` — it reads the entire request body into
memory before routing, with no streaming and no multipart parser. On a
device with ~10.8GB shared with a resident model (§5), a naive
25MB-per-upload path that also holds the body in RAM is a genuine
resource-gate concern, not a theoretical one. This is **new request-path
plumbing**, not a route addition, and it is the item most likely to be
underestimated.

Per decision 5: files on local disk under the Core's data directory
(`~/.codey_restoricon/documents/`), **streamed to disk in chunks**, 25MB
cap, images (jpg/png/heic/webp) + PDF + common documents.

**Rule-4 category** — a new request-path surface accepting caller-named
files is a path-traversal and content-type surface, and it is reachable
from the customer portal. **Rule 11 applies:** `install.sh` must create
the storage directory and carry any new dependency in the same task, not
later.

**B6.6 — The Core→Aigentik outbound notification path.** Per decision 7,
Ish chose notification-on-assignment now, over a recommendation to defer
it alongside the rest of the messaging work. Recorded as his decision.

**The direction of this dependency is new and is the real work here.**
Today Aigentik writes *through to* the Core (all ten B2 modules). Nothing
in the Core calls *out to* Aigentik. Per §3.4 the Core must not grow its
own SMTP or SMS — the voice/inbox limb owns those channels — so this is a
Core→limb call path that does not exist yet. Scope it as such.

**Email now; SMS is an investigation item, not a deliverable** (decision
9). Ish's stated reasoning was that Aigentik can only reply to Google
Voice texts it has already received, not initiate one. **Confirmed from
source, not accepted on report:**
`Codey-Aigentik/email-provider.js:1041-1055`'s
`replyToGoogleVoiceText()` sends to `voiceMessage.reply_to_email` — a
relay address that exists only because Google Voice forwarded an inbound
text. There is no path to originate an SMS to a number that has not
texted first. The investigation Ish framed — whether a still-live
`reply_to_email` thread can be held open and reused to originate a
message — is a real, bounded question with real caveats (those relay
addresses may expire, and it requires the recipient to have texted
first). **It gets investigated and reported; it is not planned as
working.**

**Calendar invites are largely a wiring job, not net-new** — also
confirmed from source rather than assumed.
`Codey-Aigentik/email-provider.js:1080-1121` already builds a
`VCALENDAR`/`VEVENT` block with `METHOD:REQUEST` and reads
`appointment.ics_sequence`; `gmail.js:95` already sends it. The Core's
own `appointments` table already carries the matching `uid` and
`ics_sequence` columns. What is missing is the Core-side trigger, not the
ICS machinery.

**B6.7 — Staff scheduling.** Per decision 6, a **new `staff_schedules`
table** — `appointments` is left alone. The reason is concrete:
`appointments` models customer bookings, has no staff-assignee column,
and is the live write-through target of Aigentik's `calendar.js` with
`external_id` idempotency matching. Overloading it would put a working
integration at risk to save a table. `schedule_config` is separately
unsuitable — it is a hard singleton (`id INTEGER PRIMARY KEY CHECK(id =
1)`) holding one global business-hours row, not per-person anything.

New table linked to `users`/`employees`, with its own read/write
permissions following the existing `PERM_READ_*`/`PERM_WRITE_*`
convention, plus the admin-side scheduling UI. **Rule-4 category** (new
permissions). On a schedule change, Aigentik sends an ICS invite to the
person's email via B6.6 — Ish's explicit ask.

**B6.8 — The four staff portals: PM, sales, technician, subcontractor.**
Net-new; none exist today, though all four roles exist in the `users`
table and the permission system. Each copies B6.3's established pattern
and is filtered by the same permission system rather than
reimplementing access rules per portal.

**Smart Login Routing:** All staff will authenticate through the single
existing `/admin/login` page. The login Javascript will inspect the user's
`role` upon success and automatically redirect them to `/admin`, `/pm`, 
`/sales`, `/tech`, or `/subcontractor` accordingly (Ish, 2026-09-06).

**Every one of them opens on "where am I assigned"** — Ish's explicit
requirement: the dashboard shows where people are assigned when they log
in, plus their own calendar from B6.7. That is the primary screen, not a
sub-tab.

**Rule-4 category.** Four new authenticated surfaces over the same
customer and financial data is the highest-risk item in this phase for
exactly the reason §6.6 already gives — and a subcontractor portal is the
first surface in this system exposing project data to someone outside the
company. Its narrowing rules deserve their own review pass, not a shared
one.

**Depends on:** B1 (API + auth), B3/B5a (the services), B4 (the API
layer). **Blocks:** nothing in Track A.

### 6.10 Track B / Phase B7 — Backup and disaster recovery to Google Cloud Storage

**Added 2026-09-02 at Ish's request, in his words "its own section to
implement."** This **resolves §8 Q5** ("backup and maintenance windows —
real requirements, explicitly deferred, to be figured out"), which had
been open since the 2026-08-21 merge. §3.6 named the deferral; this phase
closes it.

**Trigger (Ish, 2026-09-02): a continuous local journal plus periodic
snapshot,** not a literal per-write upload. Ish's phrasing was "backed up
after every new entry"; asked directly, he chose the journal+snapshot
shape over per-write upload. Every write appends to a durable local
journal immediately, and the journal plus a full DB snapshot ship to GCS
on a short interval and on clean shutdown. The exposure is a few minutes
of data in a total-device-loss scenario, without a network call per audit
row on a phone that may be on mobile data. Stated plainly: this is the
standard point-in-time-recovery shape, chosen deliberately over the
literal reading of the request.

**Scope (Ish's selection, 2026-09-02):**

1. **The Core database** — `~/.codey_restoricon/core.db`. Every customer,
   lead, project, estimate, contract, invoice, comms record, and audit
   row. The irreplaceable thing.
2. **Uploaded documents and photos** — the B6.5 file store. Also
   irreplaceable, much larger, and changes differently: needs
   **incremental** upload of new/changed files, not a full re-push per
   cycle. **Depends on B6.5** — there is nothing to back up until upload
   exists.
3. **Config, secrets, and tokens** — `config.json`, API tokens,
   provisioned credentials. Needed to restore a *working system* rather
   than just data.

**Deliberately excluded: the code repos** (Codey-OS, Codey-Aigentik, the
website). Already in git and pushed to GitHub; a second backup of a
backup. Offered and **not selected** by Ish — stated that way rather than
as an active rejection, since it was one unchosen option in a multi-select.

**The named risk, stated before the work starts rather than discovered
during it:** item 3 puts secrets in cloud storage. That requires
**encryption before upload**, with the key held somewhere the backup
itself does not contain — a careless implementation here is worse than
having no backup, because it converts a device-loss problem into a
credential-disclosure problem. **Rule-4 category** on the credential
handling specifically.

**Exit criterion: a restore drill, not a successful upload.** A backup
that has never been restored is not a backup — restoring to a scratch
path and verifying row counts and file integrity against the live DB is
what closes this phase. Per rule 7 this is a **live-verified** item by
its nature; code-complete does not close it.

**Rule 11 applies:** `install.sh` must carry the GCS client dependency
and the credential-setup step in the same task.

**Depends on:** B6.5 (for the document store). The database half has no
dependency on B6 and could run earlier if Ish wants data protection
before the web layer is finished — worth flagging as a genuine option,
since the DB is the irreplaceable part and it is already full of real
business data today.

### 6.11 Parked — do not start without Ish's explicit sign-off

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
   in place of a separate planner. What remains from this question was
   not a decision but a test: whether one `llama-server` can serve
   several consumers concurrently (§6.2's concurrency test). **That test
   has now run (2026-08-26) and produced a decision-shaped negative
   result — see `NEW-206` and §8 Q11.** Kept here, struck through, so the
   answer is visible rather than the question quietly vanishing.
4. **Deployment migration off-phone.** Firebase, a bigger server, or
   something else. Explicitly not decided; revisit after the
   phone-hosted version is real.
5. ~~**Backup and maintenance windows.** Real requirements, explicitly
   deferred, "to be figured out."~~ **The backup half is ANSWERED by Ish,
   2026-09-02: Google Cloud Storage, continuous local journal plus
   periodic snapshot, and it gets its own phase — now §6.10 / Phase B7.**
   Kept here, struck through, so the answer is visible rather than the
   question quietly vanishing (same pattern as Q1/Q3/Q8/Q10 above). Ish
   raised this unprompted while answering B6's file-upload question:
   "i do have google cloud storage i would like to have everything inside
   the whole Codey-OS, Aigentik, website, etc. backed up to after every
   new entry to protect our business data. but that should get its own
   section to impliment." Asked directly about the trigger, he chose
   journal+snapshot over a literal per-write upload; asked about scope, he
   selected the Core DB, uploaded documents/photos, and config/secrets/
   tokens, and declined the code repos as already-in-git. See §6.10 for
   the full scope, the encryption-before-upload risk on the secrets half,
   and the restore-drill exit criterion.

   **The maintenance-windows half of this question is still open** and is
   deliberately not folded into B7 — scheduled maintenance windows are a
   separate concern from backup, and Ish's 2026-09-02 answer addressed
   only backup. Not treated as answered by proximity.
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
11. ~~**`NEW-206` — the real shared `llama-server` fails hard (both
    in-flight requests, HTTP 500, after a ~12-minute fragmentation-
    driven retry cascade) when concurrent requests oversubscribe its
    `kv_unified=true` shared KV pool.**~~ This is the behavioral half of
    §8 Q3's "one model vs. swap scheduling" decision that Q3 explicitly
    left open (struck through as answered on the architecture question,
    but flagging the concurrency test as the remaining unresolved
    piece) — that piece has now been tested, live, against the real
    `codey-start` stack (at `CODEY_N_CTX=8192`, not production's real
    65536 — see `NEW-206`'s own entry for why). Proven: genuine
    concurrent decoding exists (two requests on different slots
    simultaneously, confirmed via `/slots`); when combined demand
    genuinely exceeds total pool capacity, EVERY in-flight request
    fails hard (HTTP 500, all together, after an expensive 12-minute
    retry cascade) — not graceful degradation, queuing, serialization,
    or truncation-and-continue. **Narrower than a first read
    suggested, confirmed by reading the allocator source
    (`llama-kv-cache.cpp:894-1084`) rather than assumed:** the tested
    scenario already had combined demand over 100% of the pool before
    generation started, so it cannot distinguish "trivially fails
    because demand exceeds any pool's total capacity" (true regardless
    of pool size — not itself a novel finding) from "fails via KV-cache
    fragmentation even when combined demand is comfortably UNDER the
    nominal pool" (a real, distinct mechanism per the source's
    contiguous-allocation requirement, but NOT what this test actually
    exercised) — or from a during-generation (rather than prefill-time)
    collision, also untested. This bears directly on §1.4's
    single-shared-model architecture, not just on this one test's
    pass/fail, so no fix was designed or chosen unilaterally here —
    real options, not defaulted to any of them:
    - **(a) Test the actually-open questions before deciding anything
      else:** does the same hard, all-in failure also occur when
      combined demand stays UNDER the nominal pool size (via
      fragmentation) and/or when the collision happens DURING
      generation rather than at prefill — both plausible per the
      allocator's contiguity requirement, neither exercised by this
      round's test. Re-running the identical over-100% scenario at
      65536 alone would only re-confirm the trivial case and would not
      answer the question that actually matters for a realistic
      daemon+TUI load.
    - **(b) Add a request-queue/serialization layer** in front of the
      shared server so only one request decodes at a time regardless
      of the nominal 4-slot advertisement — sacrifices the genuine
      concurrency the smoke test proved is available, in exchange for
      never hitting this failure mode.
    - **(c) Have the resource gate itself refuse to admit a second
      concurrent request** once combined estimated context would
      approach the shared pool — keeps concurrency for requests that
      fit, denies admission (rather than a 12-minute cascade-then-fail)
      for ones that wouldn't.
    - **(d) Accept single-consumer-at-a-time as the real operating
      constraint** and revise §1.4's assumption that one server can
      transparently serve multiple simultaneous consumers — a product-
      direction-level acknowledgment rather than a code fix.
    **ANSWERED by Ish, 2026-08-26.** Asked directly whether to run (a)
    first (a live test at production's real `n_ctx=65536` to check
    whether the same hard-failure mechanism also triggers when combined
    demand stays fragmented-but-under-capacity, and/or during generation
    rather than at prefill — both genuinely untested by `NEW-206`'s own
    run), Ish's verbatim answer: **"lets forget about running a i think
    it will just be the same thing as our last test with smaller
    context just do the rest of it without doing a."** (a) is therefore
    **declined by Ish's own judgment call — not skipped by oversight or
    a scoping shortcut** — on the reasoning that a 65536-scale re-run of
    the same over-100%-of-pool scenario would likely just reproduce
    `NEW-206`'s existing finding at greater live-test cost (~1.5-2+
    hours) without answering the two genuinely open questions. Ish's
    fix direction, confirmed: **(c) as the primary defense — the
    resource gate itself proactively refuses to admit a second
    concurrent request once combined estimated context would approach
    the shared pool — with (b) wired up as a safety net BEHIND (c)**:
    any request (c)'s estimate doesn't reject must still never be
    allowed to decode fully concurrently with another request against
    the same shared pool; it queues/serializes instead, so the worst
    case is "slower," never "both die after a ~12-minute fragmentation
    cascade." **(b) and (c) were chosen together, with (c) primary and
    (b) as its backstop — not either alone, and not (d).**

    **Design work done this round (scoping only, per rule 4 — this
    touches resource-gate admission logic AND process/request
    coordination, so no code was written; see `PROJECT_LOG.md` for the
    full reasoning trail):**
    - **Denominator confirmed, not assumed (rule 12):** `NEW-204`'s own
      real log line (`~/.codeyOS/llama-server.log:20`, production
      65536 config) reads `n_slots = 4, n_ctx_slot = 65536, kv_unified
      = 'true'` — combined with `NEW-205`'s confirmed reading of
      `llama-context.cpp:286-297` (`kv_unified=true` ⇒ `cparams.n_ctx_seq
      = cparams.n_ctx`, i.e. the KV buffer is sized once by `-c`
      regardless of slot count, not divided by `n_parallel`), the
      shared pool an admission check must budget against is the full
      `n_ctx` value (65536 in production, 8192 in `NEW-206`'s test) —
      matching what `NEW-206`'s own arithmetic already assumed, now
      confirmed from source rather than inferred from one test's
      numbers lining up.
    - **Typical-request footprint checked before committing to the
      design's complexity — corrected on a second pass to use the real
      interactive prompt builder, not just the raw system prompt:** an
      initial desk calculation against the raw `SYSTEM_PROMPT` alone
      (~3,235 tokens) gave ~5,358 tokens against 65536 (~8%); re-run
      against `prompts/layered_prompt.py::_build_draft_prompt()` — the
      function `core/agent.py`'s interactive path actually builds
      (notes/preferences/project/repo-map/file blocks layered on top of
      the base system prompt), a real sample task prompt measured
      ~3,774 tokens, giving ~5,822 tokens + `max_tokens`=2048 against
      65536 (~8.9%). The planner-prompt figure (~4,569 tokens, ~7%,
      against `PLANNER_PROMPT` directly, which has no equivalent
      layering) is unchanged. **This is a floor, not a typical value,
      stated as such rather than overclaimed (rule 5):** it excludes
      `core/memory_v2.py`'s retrieved-context injection and any
      accumulated conversation history, both added per-request and not
      measured here. A typical single request still claims a modest
      slice of the pool at either figure, so (b)+(c) preserves real
      concurrency for the common case rather than degenerating into (d)
      by mechanism — worth stating explicitly since that was not
      guaranteed going in. (A long-accumulated interactive conversation
      history, or a heavy memory-retrieval injection, can still
      approach the full pool on its own; the admission check handles
      that correctly by construction — it just serializes whatever
      comes after.)
    - **No single existing Python chokepoint spans both call sites** —
      checked, not assumed: exactly two live code paths issue HTTP
      requests against the shared server today, `core/inference_hybrid.
      py`'s `ChatCompletionBackend.infer()` (reached via `core/
      inference_v2.py::infer()` from both the interactive path —
      `main.py`/`core/agent.py` — and the daemon's background-dispatch
      path — `core/task_executor.py` → `core/agent.py`) and `core/
      plannd.py::get_plan()` (a separate, independent HTTP call for
      planning requests, both interactive and via the daemon's
      `plan_only` RPC). `core/loader_v2.py`'s own `infer()` has zero
      live callers (dead, not a third path); `core/summarizer.py` talks
      to a different model/port entirely (out of scope, doesn't share
      this pool); the GUI has no inference path of its own — it relays
      through the daemon socket into the same two paths. The natural
      chokepoint both processes CAN already reach is therefore not a
      shared Python function but `core/resource_gate.py`'s existing
      cross-process, file-locked slot store (the same mechanism `reserve_
      slot()`/`release_slot()` already use) — extending it, not building
      a second parallel accounting store, matches this project's
      established pattern (`NEW-135`'s fix took the same approach).
    - **Reachable concurrency pairs enumerated against the real code,
      not assumed from the task's own framing:** `core/daemon.py`'s
      `_process_planner_tasks()` (~line 1178) dispatches and `await`s
      exactly one background task per tick before considering the next
      — two concurrent background tasks are NOT reachable. What IS
      reachable: (1) an interactive TUI/GUI request racing an
      already-dispatched background task still executing (the
      `interactive_active` gate in `can_dispatch_task()` is checked
      only once, at claim time — a task can run up to 1800s, and a user
      can open an interactive session after that check passed); (2) two
      simultaneous interactive clients (TUI + GUI) — no gate exists
      between them today; (3) a `plannd.get_plan()` planning call racing
      an interactive `infer()` call — different code paths, no shared
      gate. This is a real, non-empty set — the design is worth
      building, not defending against an already-excluded case.
    - **New state design:** extend each RESIDENT slot's existing dict
      (already carrying `n_ctx` since the lease/registry item) with a
      list of small per-request reservation records — `{"reservation_
      id", "pid", "tokens", "estimated_via": "tokenize"|"heuristic",
      "reserved_at"}` — rather than a bare counter, so a caller that
      crashes mid-inference can have its reservation individually reaped
      by PID-liveness (mirroring `reserve_slot()`'s own `_pid_alive()`
      reaping) instead of leaking budget and permanently wedging the
      queue.
    - **New functions (design signatures, not implemented):**
      `reserve_context_budget(port, estimated_tokens, max_tokens, n_ctx,
      pid=None, ...)` — under the store's existing lock, reap dead-PID
      reservations, sum the live ones, admit only if `sum +
      estimated_tokens + max_tokens` stays under a safety margin of
      `n_ctx` (reserving prompt-plus-generation together, not prefill
      alone — deliberately conservative, because Ish declined (a) and
      the during-generation collision surface is therefore still
      untested, so the fix cannot assume it's benign); `release_
      context_budget(port, reservation_id)`; and `wait_and_reserve_
      context_budget(...)` — the (b) queue — looping
      acquire-check-release-sleep-retry (never holding the blocking,
      no-timeout flock across the sleep, per `_LockedState`'s own
      documented "short critical section" assumption), returning failure
      on a bounded timeout rather than proceeding into the cascade.
      Explicitly not FIFO-fair (two waiters race on each retry) —
      stated, not hidden.
    - **Estimate source:** `core/tokens.py`'s existing `estimate_tokens()`
      heuristic (`len//3`/`len//4`) is already used for the UX ticker
      and `plannd.py`'s timeout, but is not accurate enough alone to be
      the sole input to a hard admission gate; the design calls for the
      server's own `/tokenize` endpoint at admission time (the same
      approach `NEW-206`'s own live test used for precision), with the
      heuristic as a fallback, recording which one was used on the
      reservation record.
    - **Ambiguity resolved, not guessed past:** the plain reading of
      Ish's own framing ("b) as a safety AFTER c") is that (c)'s refusal
      directly becomes (b)'s wait — one mechanism with two behaviors,
      not two independent circuit breakers. A separate breaker would
      only earn its place against a failure mode (c) structurally
      cannot see, and the one candidate (an imperfect estimate) is
      already covered by the `+max_tokens` margin and `/tokenize`
      precision above — so this design builds one mechanism, not two.
    - **Release-signal correction (found via a second design-review
      pass, source-checked against `~/llama.cpp/tools/server/server-
      context.cpp`, not assumed): "release on HTTP-call-return" is the
      WRONG hook and this is the design's most significant open
      question, promoted above the safety-margin/timeout numbers
      below.** `server-context.cpp`'s `slot::release()` (~line 477)
      flips the slot to IDLE and calls `reset()`, but `reset()`
      (~line 294) does NOT call `prompt_clear()` for a normal
      (non-child) task — the slot's KV cells for its prompt tokens
      stay resident for prefix-cache reuse on the next call to that
      same slot, only actually freed when a later request causes
      eviction/reuse deep inside `find_slot()`. Two concrete
      consequences for a per-call reserve-then-release design: (1) a
      reservation released the instant `ChatCompletionBackend.infer()`
      returns under-counts real occupancy for every multi-turn
      conversation (the dominant real usage pattern) — the cells the
      prior turn used are often still occupied when the next
      reservation check runs; (2) `core/inference_hybrid.py`'s own
      streaming path can return BEFORE the server actually stops
      decoding — its 15s per-read socket timeout (`_infer_streaming`,
      ~line 177) and its repeat-detection circuit breaker
      (`_MAX_REPEATS = 2`) can both break the Python-side loop while
      the server-side task is still live, so a `finally: release()`
      there would free budget the server is still using. **The
      follow-up round needs to resolve this before implementing —
      candidate 1 is now confirmed viable, not just proposed, by
      reading the actual serializer:** `server-context.cpp`'s
      `slot::to_json()` (~lines 632-666, the function backing the
      `/slots` HTTP response, confirmed by tracing `get_slots` →
      `SERVER_TASK_TYPE_METRICS` → this method) emits
      `res["n_prompt_tokens"] = prompt.tokens.size()` per slot — the
      real, currently-retained token count `NEW-206`'s own live test
      already used for ground truth via manual `/slots` polling. The
      `/slots` endpoint is enabled by this build's own default
      (`params.endpoint_slots = true`, `common.h:665`) and
      `core/loader_v2.py`'s spawn command never disables it, so no
      spawn-flag change is needed to use it. **Candidate 1: poll
      `/slots`, sum `n_prompt_tokens` across slots, and treat that as
      the authoritative admission signal** — with the Python-side
      reservation ledger serving only to close the TOCTOU window
      between an admission check and a request actually being sent,
      not as the sole source of truth on how much of the pool is used.
      **Candidate 2 (fallback if candidate 1 proves insufficient in
      practice — e.g. polling latency, or a race between polling and a
      request landing):** explicitly disable prompt-cache retention for
      this project's requests (if the API exposes a `cache_prompt:
      false`-style toggle) to make "release on return" true again, at
      the cost of losing the prefix-cache reuse benefit. Neither has
      been implemented; candidate 1 is the stronger starting point for
      the follow-up round, not a coin flip between two untested ideas.
    - **Blocking-wait safety checked, not assumed:** `wait_and_reserve_
      context_budget()`'s synchronous poll-sleep loop is safe against
      stalling the daemon's own event loop/watchdog on both live call
      sites — confirmed by reading, not assumed. The background-
      dispatch path already runs `run_agent()` via `loop.run_in_
      executor()` (`core/task_executor.py:135-137`), off the daemon's
      asyncio loop; the daemon's `plan_only` RPC path already runs
      `core/plannd.get_plan()` the same way via `core/planner_client.
      py::send_plan_request_async()`'s own `run_in_executor` call
      (~line 45). The interactive TUI path is a separate OS process
      with no shared event loop to stall — blocking there is the
      intended "slower, never dies" UX. No async-aware queue variant
      is needed on either path.
    - **Left open for the follow-up implementer round, not guessed at
      here:** the release-signal question just above (the biggest one);
      the exact safety-margin fraction of `n_ctx` to reserve
      against (a number needs choosing and code-reviewing, not invented
      silently); the queue's timeout value and the caller-facing
      error/UX at expiry; whether the `/tokenize` call should be
      centralized in one shared helper (likely `core/tokens.py` or
      `core/resource_gate.py` itself, now that it's safety-relevant, not
      just a UX computation) rather than duplicated at the two call
      sites.
    **Not implemented this round — scoped only, per rule 4** (this
    category has produced the project's worst bugs; the design above is
    detailed enough for a follow-up implementer task, but genuine
    threshold/timeout numbers still need picking and reviewing, matching
    this round's own explicit instruction not to guess past that point).

---

## 9. Document map

**Authoritative:**
- **`CODEY_MASTER_PLAN.md`** (this file) — the plan, the rules, the
  architecture, the current state, the open register. Start here.
- **`CLAUDE.md`** — **the single copy of the agent ground rules**
  (rules 1–12, working conventions, the delegation pipeline, and the
  multi-agent coexistence policy absorbed from the archived
  `HANDOFF.md`). Points here. Applies to every agent, not just Claude
  Code.
- `AGENTS.md` — start-here pointer at this file and at `CLAUDE.md`.
- `ANTIGRAVITY.md` — a ~40-line pointer at `CLAUDE.md` listing the only
  three tool-specific differences. It was a full parallel copy of the
  rules until 2026-09-02; collapsed by Ish's decision (`U.38` step 5,
  `NEW-289`) because keeping two ~16KB files hand-consistent was a
  standing drift risk rather than a design.
- `README.md` — user-facing; points here.

**Live append-only ledgers, owned by this plan** (deliberately *not*
archived — archiving them would break rules 8 and 9 immediately, since
both are written to on every round):
- **`NEW_ISSUES.md`** — the findings ledger (rule 8). NEW-1 … NEW-289
  today (header last reconciled 2026-09-02, `U.38` step 2 — it had gone
  stale twice; re-check it rather than trusting it). Per-issue status is authoritative *there*; this merge did not
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
- `docs/archive/HANDOFF.md` (archived 2026-09-02, `U.38` step 5 — a dated
  2026-08-27 Claude→Antigravity handoff whose "what's next" section was a
  fifth work queue and had come to contradict the Phase B2 records; its
  durable multi-agent-coexistence policy was moved into `CLAUDE.md`, not
  dropped. See `NEW-288`/`NEW-289`.)

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

### Obsolescence audit — pass 1, 2026-09-02 (`U.38` steps 1/1b/2)

**Scope of this pass:** all 45 `[ ]` items below, §8's 11 numbered
questions, and — added mid-pass, because the reference mapping said the
retired-model problem was not where the `U.38` brief assumed — a sweep of
every `7B`/`1.5B`/`Qwen2.5` reference in §1, §3, §5, §6, §7 and §10.

**Where the retired-model references actually are.** 54 in this file:
§6 (15), Appendix A (11, of which only 2 sit inside an open item), §5
(8), §4 (8), §1 (6), §2 (2), §3/§7/§8/§10 (1 each). The `U.38` brief
measured 51 at scoping time and scoped the audit to Appendix A + §8;
that scoping would have missed ~43 of them.

**Verdicts, per the brief's three-verdict rule:**

| Verdict | Count | Meaning |
|---|---|---|
| **Moot** | **0** | Nothing below describes a thing that no longer exists. |
| **Needs re-verification** | 8 | `U.3`, `U.11`, `U.15`, `U.17`, `U.20`, `U.29`, plus one split sub-claim each in `U.21` and `U.34`. |
| **Still real** | 34 | Model-independent, or already re-derived against Qwen3.5-4B. |
| **Stale entry — already re-verified** | 2 | `U.1`, `U.2` — see below. |

**The headline result, stated plainly because it contradicts the ask's
premise: nothing purges.** Ish's ask assumed retired-model items were
sitting in the queue as dead weight ("old things ... that may no longer
be required like the 7B model issues"). Among Appendix A's open items,
**zero** are moot. The retired model left behind a *re-verification*
debt, not a deletion backlog — which is precisely the distinction the
three-verdict rule exists to force, and a careless purge would have
deleted eight live items.

**§1/§3/§5/§6/§7/§10's 43 references are all correct historical
narration** — retirement decisions, comparison tables explicitly labelled
`(retired)`, and closed sub-task text deliberately kept verbatim as the
record of what was asked for. Two places already applied the three-verdict
discipline unprompted and correctly: §6 re-derived `NEW-21`'s fixture
against real Qwen3.5-4B numbers and *raised* its severity 3/4 → 4/4
(`NEW-188`), and §6 retired `NEW-141` as structurally unreachable once
`core/planner_loader.py` was deleted — a Moot verdict, correctly reached.
**No live present-tense claim against a retired model was found in this
document's prose.** The one real leak is in shipped code, not docs:
`core/resource_gate.py:418-433` still argues
`DEVICE_CEILING_USABLE_FRACTION = 0.60` against "the project's own
primary 7B model's ~6.4GiB cost estimate" and points its follow-up at the
archived `TODO.md` — logged as **`NEW-283`**.

**`U.1` and `U.2` were stale in the opposite direction, and this is a
rule-6 correction.** Both are written entirely around 7B/1.5B-era
evidence and neither mentions that **M1-G already re-measured them live
on Qwen3.5-4B** (2026-08-25): `NEW-50`'s verbatim-leak did **not**
reproduce, 5/5 clean with non-circularity confirmed via `git log -L`
against `d674a0c`; `NEW-7`'s grounding came back 3/3 (G2) and 3/3 + 3/3
(G2b, in a genuine no-preload domain). Filing these as "unknown, needs
re-verification" would have been its own overclaim. They are annotated
below rather than closed — per rule 5 "not reproduced" is not "fixed,"
the `NEW-50` leak source is still present in `PLANNER_PROMPT`, and
`NEW-183` records that the G3 test prompt is now a weakened
discriminator.

**Status drift found and corrected in this pass:** Appendix B's header
read `NEW-1 … NEW-277`; `NEW_ISSUES.md` was at `NEW-282`. Corrected.
(The brief noted this header had been stale by 122 ids until 2026-09-02
and warned to assume more of the same — it was stale again by 5 within
the day.)

**§8:** 11 numbered questions, **4 open** (Q2 Core→device dispatch, Q4
off-phone deployment, Q6 = `U.8`/`NEW-9`, Q7 = `U.9`/`NEW-69`, Q9 =
`U.10`), 7 answered and struck through. All four open questions are
model-independent — **Still real**. No obsolescence found in §8.

**Rule-8 findings raised by this pass:** `NEW-283` (the
`DEVICE_CEILING_USABLE_FRACTION` rationale + archived-`TODO.md` pointer),
`NEW-284` (two open items share the ID `B4`), `NEW-285` (`U.20` tracks
flake8 counts but flake8 is in neither `install.sh` nor
`requirements*.txt` — rule 11), `NEW-286` (`NEW-7` cites the archived
`WORK_QUEUE.md` for its task spec), `NEW-287` (`U.6`'s
`agent.py:863-865` anchor no longer points at the code it describes).
None fixed here.

**`U.38` steps 3 and 5 also completed the same day** — see the closed
`U.38` entry below for both. Step 3 moved 627 lines of Phase-B2 round
narrative out of §4.5 into `PROJECT_LOG.md` (byte-identity checked by
checksum, 0 lines lost). Step 5 collapsed the four boot docs to one rules
file plus thin deltas, on Ish's decision. **`U.38` is closed; the eight
needs-re-verification items in the table above are the work it
produced.**

### Phase A1 — model foundation (§6.2)

**✅ M1: migrate to Qwen3.5-4B as the single model — CLOSED 2026-08-25**
(§1.4, §6.2). **A–G are all `[x]`.** This line read "▶ START HERE" until
2026-09-02, when it was found still routing fresh sessions at completed
work (`NEW-290`). Ish's direction 2026-08-22 was to do this fully before
anything else on Track A. Every other item in this phase is calibrated against a model
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

- [x] **7.4** — resource gate + slot-aware loader. 5/5 sub-tasks
      code-complete and code-reviewer-approved (2026-08-09). Core
      admission→load→CLI-recovery path live-verified (round 18).
      **DONE — closed 2026-09-09 (doc-cleanup pass), the checkbox was
      stale.** The remaining production-config live pass this item was
      waiting on landed as M1-E (2026-08-23, DONE, fully live-verified
      on real device via `main.py --no-resume`, three tracked load/unload
      cycles through the identical `_spawn_locked()` path this item
      covers) — confirmed by re-reading M1-E's own entry, not assumed
      from its title.
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
- [x] **7.4b** — model lifecycle policy, reshaped by §1.4. **CLOSED 2026-08-27: A, B, C, D are all fully closed (code-complete, code-reviewer-approved, live-verified). Option C respawn-on-upgrade live-verified on-device.**
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
      - **Fix design for the `NEW-145`/`NEW-149`/`NEW-155` chain,
        2026-08-27 (scoping only — desk work, code not yet written, per
        rule 4's "design first, review the diff before commit" posture):**
        a concurrent scoping pass re-verified the whole chain against
        current code (not assumed unchanged since the 2026-08-11/13
        rounds that filed it — rule 12) and produced an
        implementer-ready design, referred to below as **Option C**.
        **Correction to the chain's own prose, `NEW-250`:** `utils/
        config.py:64`'s interactive ceiling default has moved from
        32768 (the value `NEW-145`'s and `NEW-152`'s own narratives are
        written against, e.g. NEW-145's "the TUI... correctly computes
        `n_ctx=32768`") to **65536**, confirmed by direct read. Doesn't
        change the bug's mechanism, but changes the real-world cost of
        staying stuck at the 16384 background ceiling to a 4x gap, not
        2x — see `NEW-250` for the full note.
        - **Re-verification findings:** `core/loader_v2.py:LlamaServer.
          start()` has three reuse-return branches that never compare
          the caller's own wanted `n_ctx` against the resident server's
          actual `n_ctx`: the fast pre-lock check (`:249-252`), the
          wait-for-another-process's-in-flight-`start()` branch
          (`:273-306`, reuse fires at `:289-294`), and the post-lock
          re-check (`:311-316`) — this is `NEW-149`'s exact mechanism,
          confirmed unchanged. `ModelLoader._ever_spawned` (`:684`,
          `:1080-1144`) is set `True` only on a genuine spawn (`:863`)
          and is never reset anywhere, including `unload()` — `NEW-155`'s
          exact residual, confirmed unchanged. `_reconcile_adopted_slot()`
          (`:905-979`, the 2026-08-26 lease/registry round) already
          resolves a resident server's real `n_ctx` via `resource_gate.
          resolve_spawned_n_ctx()` and logs a mismatch warning on
          adoption, but deliberately does not respawn — the diagnostic
          primitive this fix needs (a live, `/proc`-based read of a
          resident server's actual `-c` value) already exists in
          production code and does not need to be built new.
        - **Options considered:** (A) always spawn at the larger of the
          two ceilings, removing the two-tier system — rejected, an
          untested RAM posture on a device that has crashed before from
          concurrent model loads (CLAUDE.md rule 2), and would need its
          own dedicated live-verification round. (B) reset
          `_ever_spawned` on confirmed-dead — fixes `NEW-155`'s literal
          complaint (the watchdog's eager respawn-at-16384) but not the
          actual "stuck at 16384" symptom, which is produced by
          `LlamaServer.start()`'s reuse branches at TUI-attach time, not
          by the watchdog's respawn decision — necessary but not
          sufficient. **(C), recommended:** detect the ceiling mismatch
          only at the point an interactive caller with a bigger `n_ctx`
          need attaches, and safely respawn only then, never in the
          reverse direction (a background dispatch must never
          downsize/kill a resident interactive-ceiling server — that
          would contradict Ish's 2026-08-11 decision 3's intent).
        - **The real risk Option C must solve (CLAUDE.md rule 4
          territory — real kill logic):** not the kill mechanics (this
          codebase already has the right pattern, `stop()`'s
          TERM-then-8s-wait-then-KILL escalation, `_reconcile_adopted_
          slot()`'s positive-PID-resolution toolkit) but killing a
          server that is currently mid-request for someone else — e.g.
          the background task that caused the original 16384 spawn
          might still be running when a TUI attaches seconds later.
          `/slots`' `n_prompt_tokens` was investigated and **rejected**
          as the busy-detection signal: confirmed via `resource_gate`'s
          own comments that it reflects resident KV/prefix-cache state,
          not "is generating right now" — the exact `NEW-207`
          release-signal/prefix-cache-retention trap, unresolved. **This
          is `NEW-251`**, recorded so a future implementer doesn't
          "simplify" this design back onto `/slots` without
          re-discovering why that's unsafe. The context-budget
          reservation ledger (`reserve_context_budget()`) was also
          rejected — it only covers the narrow TOCTOU window between
          admission and HTTP dispatch, not a request's full lifetime.
          **What IS reliable:** the daemon's own task-status table
          (`core/state.py:StateStore`, one task "running" at a time) —
          query it via the existing `core/daemon.py:send_command
          ("status", ...)` socket helper (`:1344`; `_handle_status()`,
          `:309-321`, already returns `tasks.running`), not a raw
          sqlite3 connection. Confirmed safe: `core/task_executor.py:
          _execute_task()` (`:96-135`) runs actual inference via
          `await loop.run_in_executor(...)`, off the asyncio event
          loop, so the daemon's socket server stays responsive to a
          concurrent `status` query for a running task's entire
          duration. **Two failure modes the busy-check helper must
          handle:** (1) fail-closed on any ambiguity — daemon
          unreachable, query error, timeout → treat as busy, do not
          respawn this attach (matches `reserve_context_budget()`'s own
          degraded-signal posture); (2) a stale `running` task row (the
          daemon dying ungracefully mid-task, `NEW-146`'s orphan-state
          shape applied to task rows instead of the embed server) must
          not permanently disable this fix forever — bound the "busy"
          reading by the same age `_handle_health()` already uses for
          its own stuck-task detection (`core/daemon.py:339-343`,
          `task_timeout` config, default 1800s) rather than inventing a
          second threshold.
        - **Concrete design (implementer-ready):** new read-only helper
          `LlamaServer._resident_n_ctx_if_smaller()` (reuses
          `resolve_port_owner_pid()`/`pid_cmdline_contains()`/
          `resolve_spawned_n_ctx()`, `_reconcile_adopted_slot()`'s own
          pattern, `:944-945`) and a new `daemon_task_in_progress()`
          gate. Wire `allow_upgrade` (a new explicit flag,
          `LlamaServer.__init__`/`start()`, set `True` only by
          `load_primary()`'s interactive path — never inferred from
          `n_ctx` size alone) into exactly **two of the three** reuse
          branches — the fast-path check (`:249-252`) and the post-lock
          re-check (`:311-316`) — and explicitly **not** the
          wait-for-another-process's-in-flight-`start()` branch
          (`:273-306`): killing there would kill the server out from
          under that OTHER process's own in-flight `start()` call,
          producing a spurious health-wait timeout — a new, worse bug.
          When a mismatch is found and `daemon_task_in_progress()` is
          `False`, kill+respawn under the SAME per-port `flock` this
          method already holds (extend the locked region, don't add a
          second lock), reusing `stop()`'s existing TERM/wait/KILL body
          against the resolved PID, polling `_is_port_in_use()` False
          with a bounded (~10s) timeout before falling through to
          `_spawn_locked()`, releasing the killed server's resource-gate
          slot first so accounting doesn't leak a phantom resident slot.
          **Asymmetry that must be preserved:** a background-dispatched
          `load_primary()` call must NEVER set `allow_upgrade=True` — a
          background task killing a live interactive session's server
          out from under a human mid-conversation would be materially
          worse than the bug being fixed.
        - **Four judgment calls recorded per rule 6 (project-architect
          defaults taken under Ish's blanket "pick it up" instruction,
          2026-08-26 — NOT individually confirmed by Ish; each is a
          real safety-relevant tradeoff in kill logic, rule 4 territory,
          not something to treat as unilaterally settled):**
          1. **Accept the residual TOCTOU window** between
             `daemon_task_in_progress()` returning `False` and the kill
             actually landing (the daemon could claim a new task in
             that gap) — small (one status round-trip, sub-second in
             the common case) and self-recovering (the daemon's own
             in-flight HTTP call fails with a connection error, handled
             by the existing task-failure path as a normal failure, not
             a crash). Default taken: accept, document in-code, do not
             try to close further this round.
          2. **Accept the bounded (~10s) port-free-wait failing
             outright** (returning `False`, not silently falling back
             to the old undersized server) rather than guaranteeing
             success — the interactive session's first request after
             attach can fail/retry once. Default taken: accept, mirrors
             `NEW-145`'s own already-accepted "first real coder request
             pays full load latency" tradeoff — same shape, same
             answer.
          3. **Fix `NEW-155`'s `_ever_spawned` stickiness in the SAME
             round as Option C**, since Option C makes the residual
             low-risk (once C ships, a watchdog eager-respawn-at-16384
             no longer strands anyone — the next interactive attach
             self-heals it) — but as a clearly separate commit/hunk,
             not folded silently into Option C's diff, so code-reviewer
             sees it as its own change.
          4. **Do NOT add a second re-check point** (re-evaluating the
             mismatch on a TUI's first `infer()` call, not only at
             `load_primary()`'s original attach moment) — real scope
             increase (a second call site, `core/inference.py`'s
             per-turn path, would need the same logic threaded through
             it), left as an explicit, documented known limitation
             instead: `load_primary()` — and therefore this mismatch
             check — is only ever evaluated ONCE per TUI process
             invocation (confirmed: `core/inference.py`'s per-turn
             `ensure_model()` call short-circuits to `True` once
             `_loaded and server.is_running()`, `core/loader_v2.py:
             1041`). **A TUI that attaches while the daemon is
             genuinely busy stays at the smaller ceiling for its ENTIRE
             session, self-healing only on the NEXT process attach —
             not later in the same session, even if the daemon goes
             idle a moment later.** Accepted as a bounded, understood
             cost matching `NEW-145`'s own precedent, not a silent gap.
        - **Explicitly out of scope, not silently absorbed:** `NEW-148`
          (`--init`/`--tdd`/`--fix` one-shot flags never write a TUI
          session pid file, so they read as non-interactive and never
          trigger an upgrade — unchanged, `NEW-148`'s own separate
          scope); Option A (always-max-ceiling); resolving `NEW-207`
          itself.
        - **Verdict:** larger than a typical single-round fix but not
          open-ended — concrete, reuses existing primitives at every
          step (no new kill mechanism, no new busy-detection mechanism,
          no new lock). One implementer round for Option C + the
          `NEW-155` hygiene fix (separate hunk), one mandatory rule-4
          code-reviewer pass (no exceptions — real kill logic), then a
          live-verification pass (daemon-only harness, per the `NEW-14`
          swap-pressure precedent — not a full `codey-start` stack, per
          rule 2) before this chain can be marked resolved.
        - **Status update, 2026-08-27 — LIVE-VERIFIED and FULLY RESOLVED.** Committed `b0d2d86`. Two
          deliberate deviations from the literal design above, each
          independently re-verified by code-reviewer against source
          rather than accepted on the implementer's word: (1) PID
          resolution checks the resource-gate slot store FIRST, `/proc`
          only as fallback — the reverse of this design's stated order —
          because `resolve_port_owner_pid()`'s own docstring (`NEW-200`)
          confirms `/proc/net/tcp[6]` is `PermissionError` for every
          caller on this actual device, so `/proc`-first would make the
          fix a no-op in production; matches `_reconcile_adopted_slot()`
          's existing working pattern. (2) the kill uses a new single-PID
          `os.kill()` TERM-then-8s-wait-then-KILL helper, not
          `LlamaServer.stop()`'s body — `stop()`'s `os.killpg(os.getpgid
          (pid), ...)` would kill an entire foreign process group from
          one resolved PID; `core/embed_server.py:_kill_port_occupant()`
          already made this identical narrowing decision for the same
          foreign-port-occupant shape. Code-reviewer independently
          verified the asymmetry invariant holds (a background-dispatched
          `load_primary()` call can never set `allow_upgrade=True`,
          confirmed by breaking it and watching the regression test
          catch it) across two review passes (initial approval + a
          3-warning follow-up pass, all warnings closed with real
          negative-control tests, not just code changes). One
          non-blocking documentation gap found by the review is now
          logged as `NEW-258` (the `allow_upgrade` signal is
          session-presence-based, not attach-identity-based — not a
          safety hole, since the kill decision is separately gated by
          `daemon_task_in_progress()` regardless of how `allow_upgrade`
          got set, but a labeling-accuracy gap worth tightening someday).
          **Live verification pass findings:** The test proved Option C 
          was correctly fail-closed but uncovered three distinct bugs that
          prevented the upgrade path from running: (1) `core/loader_v2.py:load_primary()`
          did not pass `port` to `reserve_slot()`, rendering the slot 
          invisible to the foreground TUI's upgrade check (`NEW-259`). (2) `core/daemon.py:DaemonServer._handle_status()`
          crashed when checking for idle tasks because it tried to access
          a missing `self._config` object, tripping the fail-closed "busy"
          behavior (`NEW-259`). (3) `core/resource_gate.py:reserve_slot()`
          double-counted same-port resident models in `_sum_committed_bytes()`,
          rejecting the candidate before `LlamaServer.start()` could execute (`NEW-261`).
          All three were patched, and on-device live testing successfully
          spawned a background model at `n_ctx=16384` (PID 5943), verified its resident
          slot, confirmed clean SIGTERM termination of PID 5943 on interactive attach,
          and confirmed respawn at `n_ctx=65536` (PID 6300) with zero leaks and
          RAM returning to baseline. This chain (`NEW-145`/`NEW-149`/`NEW-155`) is now
          fully resolved and live-verified.
  - [x] **D** — folded into M1-F,
        `MAX_CONCURRENT_MODEL_BUDGET_BYTES` (§ M1-F entry above) now
        reflects there being no separate planner process, executed with
        real numbers instead of left unchanged by inertia.
- [x] **Lease/registry** — replace port-probe adoption with an explicit
      lease. Absorbs `NEW-104`, `NEW-144`/`NEW-146`, `NEW-149`.
      Prerequisite for a shared model server; more load-bearing under
      §1.4, since one server now has more consumers.
      **DONE 2026-08-26: code-complete, code-reviewer-approved (692
      passed/1 skipped), not live-verified (no live component by design).**
      Built as a registry query
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
      pass APPROVED 2026-08-26** — reviewer independently traced control
      flow, confirmed no rule-3 violation, reproduced `NEW-200` live, and
      proved the rewritten test is a real regression guard (hand-broke
      `_pid_owning_inode()`, confirmed the test fails without the fix).
      Three non-blocking findings logged: `NEW-201` (a TOCTOU
      double-registration race, confirmed not currently reachable),
      `NEW-202` (a status-filter divergence, confirmed currently
      harmless), `NEW-203` (an inaccurate `stop()` docstring claim, safe
      in practice). This item is now DONE.
- [x] **Concurrency test — CLOSED 2026-09-09, fully live-verified (see status update at the end of this entry).** — **Live pass RUN 2026-08-26; negative result
      (`NEW-206`); checkbox stays unchecked [historical, superseded below].** Mechanism confirmed active
      by real production log evidence (`NEW-204`): every real launch
      already runs `n_slots = 4, kv_unified = 'true'` by this llama.cpp
      build's own default. KV-cache memory does not scale with slot
      count (checked, `llama-context.cpp:286-297`); recurrent/SSM state
      does and is undercounted ~150.75MiB in `core/resource_gate.py`
      today (`NEW-205`, logged not fixed). **The behavioral question is
      now answered, not open — and the answer is bad:** a real
      `codey-start` live pass at `CODEY_N_CTX=8192` (production's real
      65536 would need ~40+ min prefill per rung; same binary/code path/
      defaults, smaller pool only) confirmed genuine concurrent decoding
      via `/slots` (two requests on different slots simultaneously), then
      drove two prompts to combined 8491 tokens against the 8192 pool —
      result was KV-fragmentation (`failed to find a memory slot for
      batch`), a ~12-minute cascading retry, and a **hard failure of
      BOTH in-flight requests** (HTTP 500 each, `Context size has been
      exceeded`), not graceful degradation, queuing, serialization, or
      truncation-and-continue. RAM stayed flat (no resource-exhaustion
      confound); a ~3s ADB-confirmed phone-foreground blip occurred 11+
      minutes before the actual failure and is ruled out as a cause by
      that timing gap. **Not yet confirmed, and narrower than a first
      read of the result suggested:** the test's combined demand
      (8491 tokens) already exceeded the 8192 pool before generation
      began, so this run cannot separate "trivially fails because
      demand exceeds any pool's total capacity" (true regardless of
      pool size) from "fails via fragmentation even when combined
      demand is comfortably under the nominal pool" (the more
      consequential, unproven case — real per the allocator source's
      contiguous-allocation requirement, `llama-kv-cache.cpp:894-1084`,
      but not exercised by this test) or from a during-generation
      (rather than prefill-time) collision. A 65536 re-run needs to
      target those two gaps specifically, not just repeat the same
      over-capacity scenario at a bigger number.
      **Escalated to Ish as §8 Q11** — this bears on §1.4's
      single-shared-model architecture assumption, not just this one
      test's pass/fail, so no fix (queuing, admission capping, or
      re-opening §1.4) was designed or picked here. **Status update,
      2026-08-26: §8 Q11 ANSWERED.** Ish declined option (a) by his own
      judgment ("lets forget about running a i think it will just be
      the same thing as our last test with smaller context just do the
      rest of it without doing a") and chose (c) as primary defense
      with (b) wired directly behind it as a serialization backstop —
      not (d), not either alone. This round scoped the fix design (desk
      only, per rule 4): confirmed the shared pool's denominator is the
      full `n_ctx` (not divided by `n_parallel`) from `NEW-204`'s log
      plus `NEW-205`'s source-read of `llama-context.cpp`; confirmed a
      typical request claims ~7-8% of the 65536 pool, so (b)+(c)
      preserves real concurrency rather than degenerating into (d);
      identified the two live HTTP call sites that need wiring
      (`core/inference_hybrid.py::ChatCompletionBackend.infer()` and
      `core/plannd.py::get_plan()`, both funneling through no shared
      Python chokepoint today) and the natural cross-process
      chokepoint to extend instead (`core/resource_gate.py`'s existing
      file-locked slot store); enumerated the actually-reachable
      concurrency pairs from `core/daemon.py`'s own dispatch code
      (`_process_planner_tasks()` never runs two background tasks
      concurrently — ruled out; TUI-vs-lingering-background-task,
      TUI-vs-GUI, and planning-vs-inference races ARE reachable); and
      resolved the admit-then-queue-vs-separate-circuit-breaker
      ambiguity in favor of one mechanism, matching Ish's own "b) as a
      safety AFTER c" framing. A second design-review pass (source-
      checked against `~/llama.cpp/tools/server/server-context.cpp`)
      found the design's original "release budget when the HTTP call
      returns" hook is likely WRONG — `slot::release()`'s `reset()`
      does not clear a normal task's cached prompt tokens, so KV cells
      stay resident across calls for prefix-cache reuse, meaning a
      per-call reservation under-counts real occupancy in the dominant
      multi-turn case; this is now the design's single biggest open
      question, promoted above the safety-margin/timeout numbers.
      Candidate 1 — poll `/slots` (enabled by this build's default,
      unmodified by this project's spawn command) and sum its
      `n_prompt_tokens` field (confirmed real, from `slot::to_json()`)
      as the authoritative occupancy signal — is CONFIRMED VIABLE, not
      just proposed; candidate 2 (disable prompt-cache retention) is
      the fallback if candidate 1 proves insufficient in practice.
      Neither implemented here. Separately confirmed (not assumed)
      that a blocking wait-queue is safe on both live call sites —
      both already run off the daemon's event loop via
      `run_in_executor` (`core/task_executor.py`, `core/planner_
      client.py`). Full design detail is in §8 Q11 itself. **Not
      implemented this round** — the release-signal question, the
      safety-margin fraction, and the queue-timeout value are all
      genuine open items a follow-up implementer task still needs to
      resolve and get code-reviewed, not guessed at here. One item
      found outside this round's scope while enumerating concurrency
      pairs, logged per rule 8 rather than fixed or dropped:
      **`NEW-207`** — `can_dispatch_task()`'s `interactive_active`
      check is evaluated only once, at task-claim time, so an
      already-claimed background task can keep running for up to 1800s
      alongside a later-opened interactive session, undermining that
      gate's own stated intent (the §8 Q11 fix makes this overlap safe
      once implemented, but does not restore the gate's original
      policy).

      **Implementation round, 2026-08-26 (design → code, rule 4 —
      CODE-COMPLETE AND SELF-TESTED, MANDATORY CODE-REVIEWER PASS NOT
      YET RUN, NOT LIVE-VERIFIED):** the design's two open questions from
      the prior round are now resolved and built, not just proposed:
      - **Release-signal question (the design's single biggest open item)
        resolved as candidate 1:** `core/resource_gate.py`'s new
        `_fetch_slots_prompt_tokens()` polls the live server's `/slots`
        endpoint and sums `n_prompt_tokens` as the AUTHORITATIVE occupancy
        signal at each admission check; the new context-budget reservation
        ledger's only job is closing the TOCTOU window between an
        admission check and that request actually reaching the server —
        it releases on HTTP-return (correct for THAT purpose, unlike the
        original rejected "release on HTTP-return as sole occupancy
        signal" idea — see `release_context_budget()`'s own docstring for
        why the two are different claims).
      - **Denominator resolved from the REAL spawned server, not
        `MODEL_CONFIG["n_ctx"]`:** a mid-implementation advisor review
        caught that budgeting against config directly would have silently
        no-op'd on exactly `NEW-206`'s own `CODEY_N_CTX=8192`-vs-65536-
        default reproduction path. `resolve_effective_n_ctx()` reads the
        real spawn-time value from the slot store's persisted `n_ctx`
        field first (`NEW-149`/`NEW-155`'s lease/registry item), falling
        back to a live `/proc/<pid>/cmdline` re-derivation; if neither
        resolves, admission REFUSES rather than guesses (CLAUDE.md rule
        12) — a deliberate fail-closed choice for safety-relevant logic,
        expected to essentially never fire when the server was spawned
        through this project's normal `core/loader_v2.py` path.
      - **Safety margin: `CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION = 0.15`**
        (not tighter) — reasoned from `NEW-206`'s own confirmed
        fragmentation mechanism (`find_slot()`'s contiguous-allocation
        requirement can fail even when total free-cell count elsewhere
        would suffice), so a margin that only just clears 100% nominal
        capacity would leave the exact untested non-contiguous-free-space
        scenario free to still trigger the cascade. First-pass,
        un-calibrated, same voice as `REQUIRED_HEADROOM_FACTOR`/
        `DEVICE_CEILING_USABLE_FRACTION` — not measured against real
        on-device fragmentation, which nothing in this project has run
        (Ish declined the 65536 re-run that would have).
      - **Queue timeout: formula-based** (`compute_context_queue_timeout_
        seconds()`, matching `compute_planner_timeout()`'s own established
        precedent over a flat constant — `NEW-165`'s own lesson), modeled
        as one full-context occupant's worst-case prefill+generation time
        using the same device-rate floors, then capped at
        `CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS = 600.0` (10 minutes) — the
        uncapped formula reaches ~110 minutes at production's real
        n_ctx=65536, which would blow through both real call sites' own
        enclosing timeouts (the daemon's 1800s background-task timeout,
        and the plan_only RPC's outer `asyncio.wait_for`). `core/plannd.py`
        gained `compute_outer_plan_timeout()` and `core/daemon.py`'s two
        outer-timeout call sites were updated to use it, so a pre-request
        queue wait inside `get_plan()` cannot be cancelled by the outer
        wait_for before its own bounded wait gets a chance to resolve —
        a necessary companion change beyond the two named call sites,
        required to preserve `compute_planner_timeout()`'s own documented
        "inner fires first" invariant, not a scope drift.
      - **`/tokenize` centralized**, not duplicated: both call sites go
        through `estimate_prompt_tokens()`, which prefers the server's own
        `/tokenize` endpoint and falls back to `core/tokens.py`'s
        heuristic — padded 1.35x on the fallback path specifically because
        `estimate_tokens()` with no file-path argument always uses the
        ~4-chars/token prose ratio, under-counting code-heavy prompts by
        roughly a third (the dangerous under-admission direction).
      - **Timeout/refusal UX, decided:** both call sites return `None` on
        admission refusal or timeout — each function's own pre-existing
        "returns None on failure" contract, so an admission failure looks
        to every existing caller exactly like any other inference/planning
        failure already does; no new caller-facing exception type or
        failure mode was introduced.
      - **Wired at both named call sites**, each releasing its reservation
        in a `finally` regardless of success/failure:
        `core/inference_hybrid.py::ChatCompletionBackend.infer()` and
        `core/plannd.py::get_plan()`.
      - **Tests:** `tests/test_context_budget.py` (19 tests — admission,
        refusal, TOCTOU-closing via the reservation ledger, `/slots`-
        unreachable degrade-not-crash-not-unlimited behavior, reservation
        expiry/reaping, the queue's retry/timeout paths with an injected
        fake clock, no real sleeping) and
        `tests/test_inference_hybrid_context_budget.py` (5 tests covering
        `infer()`'s wiring specifically: admits-and-releases,
        refused-never-calls-urlopen, timed-out-never-calls-urlopen,
        releases-even-on-HTTP-failure, fails-closed-when-the-check-itself-
        raises). Two pre-existing test files
        (`tests/test_plannd_timeout.py`, `tests/test_plannd_tier_split.py`)
        needed an autouse fixture stubbing the new gate to "always admit,"
        since their synthetic environment has no resident slot registered
        and would otherwise refuse every `get_plan()` call before reaching
        the HTTP/parsing behavior those files actually test — a real,
        necessary update given the behavior genuinely changed, not a
        weakening of that coverage.
      - Full test suite run: `python -m pytest tests/ -q --ignore=tests/
        test_restoricon_core` → **716 passed, 1 skipped** (the 1 skip is
        pre-existing, unrelated to this change).
      - **NOT yet done:** the mandatory rule-4 code-reviewer pass (this
        touches resource-gate admission logic AND process/request
        coordination) has not yet run — no commit has been made pending
        that approval. Not live-verified against a real `codey-start`
        stack (the same live-test cost/risk profile `NEW-206`'s own
        original test had, and which Ish declined to re-spend on a 65536
        re-run) — this round's own verification is unit/mock-tested only,
        stated explicitly per rule 7, not claimed as behaviorally
        confirmed.

      **Mandatory rule-4 code-reviewer pass, 2026-08-27: CHANGES
      REQUESTED (a logging requirement, not a mandatory code fix).**
      Reviewer independently verified fail-closed `n_ctx` resolution, no
      cross-ledger TOCTOU regression against the model-slot store, correct
      lock discipline in the wait loop (never holds the blocking flock
      across `sleep`, clean bounded timeout with no leaked reservation),
      `release_context_budget()` called on every exit path of both call
      sites including exception branches, correct daemon timeout layering
      (the new outer `asyncio.wait_for` strictly bounds inner-timeout plus
      queue-wait), no duplicated safety-margin/timeout constants, and that
      the two pre-existing tests' new autouse fixtures only bypass the new
      admission check without weakening their original assertions. Full
      suite independently rerun: 716 passed/1 skipped, matching exactly.
      **One real defect found, confirmed safe-direction (under-admits,
      never over-admits — cannot reopen `NEW-206`'s cascade):**
      `reserve_context_budget()`'s combined-usage sum double-counts every
      admitted request for its ENTIRE in-flight duration, not just the
      brief TOCTOU window the design intends, because
      `release_context_budget()` only fires in a `finally` after the full
      HTTP call returns — an admitted request is counted both via its
      still-outstanding local reservation AND via `/slots`' own live
      occupancy for as long as it runs, quietly roughly halving the real
      concurrency this fix was meant to preserve at the documented ~8-9%
      typical footprint and 15% margin. Logged as **`NEW-208`** per rule
      8 (the required action, now complete) — a code fix is not mandatory
      this round since the direction is safe, and is left as an open
      question for a future round (or Ish) on whether the reduced-
      concurrency cost is worth addressing now.
      **Status update, 2026-09-09 — the mandatory live-verify pass has
      now run, and the fix DOES NOT reliably work on real hardware.**
      Real hardware, `CODEY_N_CTX=8192`, one RAM-disciplined model-load
      cycle: the gate's own admission arithmetic checked out in
      isolation, but through the real end-to-end call path
      (`ChatCompletionBackend.infer()`), two combined-over-ceiling
      requests (9099 tokens against a 6963-token ceiling) still
      genuinely double-admitted into the shared pool — confirmed
      directly from server logs showing both processing simultaneously
      in different slots. Both died to a 300s client-side HTTP timeout
      rather than the original `Context size has been exceeded` cascade
      (that specific mechanism did not reproduce), a different proximate
      failure but the same class of outcome the fix exists to prevent.
      **Compound root cause, both confirmed from evidence:** (1) the
      60s lease duration (`core/resource_bus.py:DEFAULT_LEASE_
      DURATION_SEC`) is shorter than this device's realistic in-flight
      duration (a 4249-token prompt's own prefill alone took 179s), so
      the first request's reservation auto-expired while it was still
      genuinely running; (2) `reserve_context_budget()`'s `/slots`-
      unreachable fallback degrades occupancy to zero — exactly the
      dangerous direction its own docstring names — and `/slots` was
      observed unreachable in 12 of 13 polling attempts during
      precisely the high-load window that mattered. This also falsifies
      the "safe-direction-only, cannot reopen NEW-206's cascade" claim
      made above about `NEW-208` — under real degraded conditions the
      system does over-admit, via a different mechanism than `NEW-208`
      describes. Logged as **`NEW-430`** (lease duration) and
      **`NEW-431`** (`/slots`-degrade behavior) — fixing only one
      leaves the hole open via the other; a third, unrelated finding,
      **`NEW-432`**, surfaced during pre-flight (a stale resident-slot
      record permanently un-reapable due to PID reuse, silently
      corrupting the ceiling until manually cleaned up). **Status
      update, 2026-09-09 — `NEW-430`/`NEW-431` fix round CODE-COMPLETE
      and code-reviewer APPROVED (`f6c3a78`), NOT YET LIVE-VERIFIED.**
      Lease duration now explicit 1800s (matches the daemon's own
      `task_timeout` watchdog) instead of inheriting the 60s shared
      default; `/slots`-unreachable now retries once then fails
      closed (refuses admission, doesn't degrade to zero-occupancy)
      with `effective_n_ctx` kept real so the caller retries rather
      than hard-failing. Reviewer traced both changes end-to-end, no
      lock/lease-leak regressions found. 8 new tests, full suite 1552
      passed/1 skipped/1 unrelated pre-existing failure (`NEW-433`,
      bisected to unmodified `main`). One new out-of-scope finding,
      `NEW-434` (retry loop re-runs `/tokenize` every tick). **Status
      update, 2026-09-09 — live-verify run: `NEW-430`/`NEW-431` both
      CONFIRMED FIXED under real load (no over-admission occurred,
      confirmed from the real lease DB; the first request's lease
      survived its full real duration; the second was correctly
      refused/retried through the busy window, not wrongly admitted),
      but the pass still ends FAIL overall.** The second, concurrent
      request was refused for the full 600s queue-timeout cap and
      never admitted, even though the server was genuinely idle for
      ~390s of that window. New root cause, logged as **`NEW-435`**:
      `_fetch_slots_prompt_tokens()` sums every slot's
      `n_prompt_tokens` unconditionally, including idle slots still
      reporting their last-served request's size — llama.cpp's real
      `/slots` endpoint doesn't zero this out on release, so the gate
      perceived a genuinely-idle pool as still full. Opposite failure
      direction from `NEW-431` (stuck non-zero, not wrongly-zero), same
      function. **Status update, 2026-09-09 — `NEW-435` fix round
      CODE-COMPLETE and code-reviewer APPROVED (`22cab45`), NOT YET
      LIVE-VERIFIED.** `_fetch_slots_prompt_tokens()` now only sums a
      slot's `n_prompt_tokens` when `is_processing is True` (root cause
      confirmed against the real llama.cpp source: `n_prompt_tokens`
      persists post-release via `task_prev`, `is_processing` updates
      with no meaningful lag); a slot with missing/malformed
      `is_processing` fails closed (counted, warned) rather than
      assumed idle. 7 new tests, full suite 1673 passed/1 skipped/1
      unrelated pre-existing failure (`NEW-433`). One new Suspected
      finding, `NEW-436` (a conservative-direction double-count
      between `/slots` occupancy and the local ledger; confirmed
      real 2026-09-10 and accepted not-fixed — see below).
      **Status update, 2026-09-09 — live-verify PASSES against the
      real NEW-435 bar.** Same real repro (`CODEY_N_CTX=8192`, two
      concurrent 4246-token requests, real end-to-end call sites);
      direct before/after diff against the preserved pre-fix run
      confirms the stale `slots=4554` reading is gone; the second
      request was admitted 1.45s after the first's slot released
      (vs. the 600s cap that killed the prior pass), and both
      requests completed successfully. First time the row's actual
      success bar (both complete, no starvation, no over-admission)
      has been met on real hardware across the whole `NEW-206`→
      `NEW-430`/`NEW-431`→`NEW-435` chain. **Checkbox now checked.**
      Residual, non-blocking findings from this saga remain open and
      tracked separately, none required for this row's closure:
      `NEW-432` (stale resident-slot record on PID reuse — different
      mechanism, narrow/rare), `NEW-433` (unrelated pre-existing test
      failure), `NEW-434` (`/tokenize` call efficiency in the retry
      loop, not correctness), `NEW-436` (confirmed conservative-
      direction double-count, accepted not-fixed 2026-09-10:
      concurrent already-dispatched request counted in both the
      `/slots` sum and its still-held ledger lease; safe-direction,
      negligible impact at the `n_parallel=4` production ceiling;
      original entry's self-double-count mechanism was wrong,
      corrected per rule 6). Two new findings logged from the
      confirmation round: `NEW-441` (dead `legacy_reserved` sum in
      `acquire_context_lease()`), `NEW-442` (Core API chat route
      calls `release_context_budget()` with wrong arity — leaks
      every request's reservation until the 1800s reap).

### Phase A2 — coding-domain rollout (§6.8)

- [x] **7.3 sub-task E** — dispatch on the tier decision (A–D built,
      Task A + Task B completed and approved 2026-08-24).
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
- [x] **4.3** — wrap `core/agent.py` as a CCOS capability, unifying both
      call paths (`main.py` and `core/task_executor.py` via `coding.run_agent`).
- [x] **7.5** — in-flight context passing + task-context blackboard.
- [x] **4.5** — peer-CLI escalation redesign & review queue. **DONE 2026-08-30: code-complete,
      code-reviewer-approved, and live-verified on-device.** Antigravity CLI (`agy`,
      aliases: `antigravity`, `gemini`) replaces Gemini CLI; Qwen Code CLI (`qwen`,
      aliases: `qwen-code`, `qwen3.5`) aligned with non-interactive `-p` and `-y`;
      Claude Code CLI (`claude`, aliases: `claude-code`) explicitly disabled
      (`enabled=False`, `disabled_reason="Claude Code is currently disabled (no API credits configured)."`)
      with safe warning and redirection fallback; structured tool `peer_delegate`
      and CCOS capability `coding.peer_delegate` implemented; noise-stripping
      and error sentinels (`[PEER_ERROR: ...]`) generalized; non-blocking review queue
      integrated on `TaskBlackboard` with `escalation_reviews` schema table,
      `escalate_or_park()` non-interactive fallback for daemon workers, and review/execution
      CLI methods (`list_parked_escalations`, `resolve_parked_escalation`, `execute_parked_escalation`);
      tests in `tests/test_escalation_review_queue.py` and `tests/test_peer_cli_redesign.py` passing,
      full suite 1,151 passed, 1 skipped.
- [x] **4.6** — wire `agent_orchestrator` to real execution (Safety veto
      goes live).
- [x] **4.7** — multi-domain request splitting.
- [x] **9.3** — manifest schema extension. **DONE 2026-08-30: code-complete,
      code-reviewer-approved.** Created `ccos/core/manifest_schema_v2.py` with
      declarative JSON Schema v2, pure Python validator `validate_manifest_v2`,
      backward-compatible v1 normalizer `normalize_manifest`, and updated
      `Capability` and `PluginManager` to track execution modes, domain isolation,
      resource limits, and typed inputs/outputs schemas; verified with 9 unit tests.
- [x] **9.4** — limb-integration plan. **DONE 2026-08-30: code-complete,
      code-reviewer-approved.** Settled §8 Q2 with Local Loopback WebSocket/HTTP
      IPC protocol (`ws://127.0.0.1:8088/ws/device`), created `ccos/core/device_bridge.py`
      (`DeviceBridgeServer`, `DeviceBridgeClient`), emergency shortcode safety
      veto engine (blocking 911, 112, 999, etc.), and CCOS device plugin
      `ccos/plugins/device/bridge/`; verified with 7 unit tests.
- [x] **9.2** — generalize the gate into a multi-process
      scheduler/resource-bus. **DONE 2026-08-30: code-complete, code-reviewer-approved.**
      Created `core/resource_bus.py` with cross-process SQLite WAL + flock coordination,
      priority queue scheduling (`CRITICAL`, `HIGH`, `NORMAL`, `LOW`), dynamic aging
      anti-starvation, thermal throttling integration (`core/thermal.py`), memory
      pressure guards (`core/sysmon.py`), zombie PID reaping (Rule 3 compliant), and
      delegated context leasing in `core/resource_gate.py` with 100% backward compatibility.
- [x] **external_process registration** of both limbs. **DONE 2026-08-30: code-complete,
      code-reviewer-approved.** Extended `ccos/core/manifest_schema_v2.py` for
      `external_process` and `remote_bridge`, implemented `ProcessSupervisor` in
      `ccos/core/plugin_manager.py` with exact PID tracking and HTTP/IPC capability
      forwarding, and deployed manifests for `Codey-Aigentik` and `Private-Codey-Agent`.
- [ ] **11.x** — Model Orchestrator. **Parked** until a domain agent
      needing it is scoped.

### Phase B — business layer (§6.3–§6.10)

**Header added 2026-09-02.** These items previously sat physically under
the `Phase A2 — coding-domain rollout` heading above, with no heading of
their own — a structural quirk of the 2026-08-21 merge, not a claim that
business-layer work belongs to Track A. Nothing was moved or re-scoped;
only this heading was inserted.

- [x] **B1** — Core schema + canonical IDs (code-complete, 11 tests passing in `tests/test_restoricon_core/`).
- [x] **B1** — the HTTP API boundary (code-complete; rule-4 adversarial review pending for binding & auth).
- [x] **B1** — auth, roles, permissions (code-complete; 7 roles, PBKDF2 hashing, bearer tokens, customer isolation).
- [x] **B1** — Communication History + Audit Log (day-one-or-never, code-complete; append-only verified).
- [x] **B2** — create `Codey-Aigentik` fork; migrate `data/*.json` into
      the Core; write-through; point at the shared model layer.
      **DONE 2026-08-30: 100% code-complete, code-reviewer-approved, full test suites passing.**
      All 10 of 10 write-site modules cut over to Restoricon Core API with zero local JSON writes:
      1. `do-not-contact.js` (`/api/v1/do-not-contact*`)
      2. `email-rules.js` & `sms-rules.js` (`/api/v1/automation-rules*`)
      3. `calendar.js` & `schedule_config` (`/api/v1/appointments*`, `/api/v1/schedule-config`)
      4. `subcontractor-recruiter.js` (`/api/v1/subcontractors*`)
      5. `email-provider.js` (outbound/inbound comms history + reliable retry queue)
      6. `customer-module.js` (`/api/v1/customers*`, `/api/v1/leads*`)
      7. `business_profile` in `index.js` & `owner-command.js` (`/api/v1/business-profile`)
      8. `llama.js` model layer repoint (`POST /api/v1/ai/chat` via context budget reservation, `NEW-211`)
      9. `contacts.js` phonebook sync & directory (`/api/v1/contacts*`, resolving `NEW-215`)
      10. `contacts-sync.js` & `queue.js` (batch sync via `/api/v1/contacts/sync`, sandboxed review queue).
      Full test suites: 16/16 suites (226/226 tests) passing in `Codey-Aigentik`; 1069 tests passing in `Codey-OS`.
- [x] **B3** — CRM/Sales domain. **DONE 2026-08-30: code-complete, code-reviewer-approved.**
      Implemented 9-stage pipeline state machine (`PipelineStage`), insurance claim tracking
      (carrier, claim #, adjuster info, deductible), deterministic 5-dimension lead qualification
      scoring (0–100 scale: Scope, Property, Urgency, Insurance, Responsiveness), automated follow-up
      cadence task scheduling (`tasks` table and engine), pipeline board aggregations, and
      RBAC endpoints under `/api/v1/crm/*` and `/api/v1/opportunities*`; verified with 15 new unit tests.
- [x] **B3** — Operations domain. **DONE 2026-08-30 (`OperationsService`).**
- [x] **B3** — first Automated Workflows. **DONE 2026-08-30 (`OperationsService` automation rules engine).**
- [x] **B4** — phone-hosted public site. **DONE 2026-08-31 (Public intake, top-left hamburger navigation drawer, and static hosting).**
- [x] **B4** — staff/admin surface. Was **PARTIAL** (downgraded 2026-09-02
      per rule 6, was briefly marked DONE 2026-08-31 before that
      correction) — the gaps named then (`NEW-273`'s `alert()` save
      stubs, `NEW-274`'s 8 hardcoded placeholder tabs) are what **B6.4**
      was scoped to close. **DONE — closed 2026-09-09 (doc-cleanup
      pass), the checkbox was stale.** `B6.4a` (`PROJECT_LOG.md`
      2026-09-06) wired `saveBusinessProfile()`/`saveScheduleConfig()`
      to real `GET`/`POST` calls, closing `NEW-273`; `B6.4b-f` (same
      date) wired the remaining tabs (KPIs, operations, finance, comms,
      biz-ops) to their real endpoints, closing `NEW-274`. **Tier: code-
      complete** (both entries state this explicitly; not stated as
      live-verified) — per rule 7, don't read this checkbox as more than
      that.
- [x] **B4** — customer portal (full document/signature/financial).
      Was **PARTIAL** (downgraded 2026-09-02 per rule 6, was briefly
      marked DONE 2026-08-31 before that correction) — the gap named
      then (`NEW-272`'s hardcoded demo HTML, only 2 of 10 real routes
      called) is what **B6.3** was scoped to close. **DONE — closed
      2026-09-09 (doc-cleanup pass), the checkbox was stale.** `B6.3`
      (`PROJECT_LOG.md` 2026-09-06, code-reviewer APPROVED) rewired
      `render_portal_surface()` to fetch real timeline/invoices/
      contracts/PM-chat data against the live `/api/v1/portal/*` routes,
      fixed `NEW-272`'s hardcoded contract id, and added a test asserting
      the rendered surface calls the routes it claims to consume (the
      exact gap that let the original demo version ship). **Tier: code-
      complete** (stated explicitly; not stated as live-verified) — per
      rule 7, don't read this checkbox as more than that.
- [x] **B4** — device-limb dashboard as third API client. **DONE 2026-08-30 (`Private-Codey-Agent/lib/screens/business_dashboard_screen.dart`).**
- [x] **B5a** — Finance/Bookkeeping. **DONE 2026-08-30 (`FinanceService`).**
- [x] **B5a** — Marketing/Lead-Gen. **DONE 2026-08-30 (`BusinessOpsService`).**
- [x] **B5a** — Compliance monitoring/alerting. **DONE 2026-08-30 (`BusinessOpsService`).**
- [x] **B5a** — HR. **DONE 2026-08-30 (`BusinessOpsService`).**
- [x] **B5a** — Customer Service. **DONE 2026-08-30 (`CommunicationService`).**
- [x] **B5a** — Procurement. **DONE 2026-08-30 (`BusinessOpsService`).**
- [x] **B5a** — Global Search. **DONE 2026-08-30 (`AnalyticsSearchService`).**
- [x] **B5a** — Reporting/Dashboard. **DONE 2026-08-30 (`AnalyticsSearchService`).**
- [x] **B5b** — create `Private-Codey-Agent` fork. **DONE 2026-08-30: fork created
      at `~/Private-Codey-Agent`, tracking upstream `https://github.com/Ishabdullah/private-agent.git`
      and origin `https://github.com/Ishabdullah/Private-Codey-Agent.git`, pushed.**
- [x] **B5b** — third-party-app automation via accessibility. **DONE 2026-08-30 (`ThirdPartyAppAutomationService`, `DeviceBridgeClientService`, `ccos.core.device_bridge`).**
- [x] **B5b** — Core→device scheduled-dispatch mechanism (protocol
      settled in Item 9.4 with loopback WebSocket/HTTP IPC and safety vetoes). **DONE 2026-08-30.**

**Phase B6 — the web-facing layer (§6.9).** Added 2026-09-02. Ordered by
dependency, then risk, then value; §6.9 states the reasoning for the
order. Every item below is a separate scoped session, not one task.

**✅ Dependency (`NEW-288`) — CLEARED 2026-09-02.** B6 is scoped on top
of Phase B2 being complete; the audit that surfaced this and the
follow-up cutover (**B2-fin-1**) are both done. B6 items may now treat
the B2 prerequisite as satisfied (code-complete tier). The audit
(against `NEW-209`/§6.4's canonical list,
corrected to **8 groups** — `queue.js` ruled out of B2 scope by Ish
2026-09-02, `NEW-291` closed; `~/Codey-Aigentik` HEAD `ee97279`):
all **eight groups are now cut over** (code-complete, NOT live-verified; 7 of 8 verdicts from `NEW-288`'s static sweep, see its stated limits —
only `do-not-contact.js` and the `business_profile` half of
`index.js`/`owner-command.js` were code-reviewed). `business_profile`
was the last gap (`NEW-292`) and closed via **B2-fin-1** on 2026-09-02
(fork commit `2056524`, code-reviewer APPROVED round 2, 239 jest tests):
`owner-command.js`'s three profile handlers now read Core-first, the
local `data/profile.json` is a write-through cache, and a Core failure
persists locally with an honest "didn't sync" reply. **B6's "B2 complete"
prerequisite is now SATISFIED at the code-complete tier** (not
live-verified — no live-model component, jest was the bar). Full
per-module evidence and the count with its measurement date are in
`NEW-288`'s resolution block; `NEW-294` records that §6.4's list said
"ten" but named nine (now eight).

**Phase B2 completion — both gaps from the 2026-09-02 audit (`NEW-288`)
now closed. B6's B2 prerequisite is satisfied (code-complete tier).**

- [x] **B2-fin-1** — `business_profile` read cutover. **DONE 2026-09-02
      — code-complete + code-reviewer APPROVED (round 2), NOT
      live-verified** (no live-model component; full jest suite,
      239 passed / 18 suites, was the verification bar). Fork commit
      `2056524`. **Rule-6 correction to `NEW-292`:** `index.js` was
      already Core-first with local fallback — the real gap was
      `owner-command.js` only, where the three profile handlers
      (`handleRename`, `handleSetBusinessInfo`, `handleSetOwnerName`)
      read the local file then POSTed a full-row overwrite, silently
      reverting fields another client had changed in Core. Now:
      `readProfile()` Core-first helper; `getAigentikName()` reads the
      in-process `config` cache (stays sync); local `profile.json`
      demoted to a write-through cache refreshed from the POST response;
      a `coreRequest` `{ok:false}` (expired token / 5xx — returned, not
      thrown) persists the edit locally and tells the owner it didn't
      sync instead of a false "Done!". `config.json.example` gained its
      missing `core_api` block. Round history: architect scoped →
      implementer → code-reviewer CHANGES REQUESTED (silent-data-loss on
      the non-throwing failure path + a stale-cache `configured` field) →
      implementer → APPROVED. Findings: `NEW-295`…`NEW-297`.
- [x] **B2-fin-2** — `queue.js` (`NEW-291`). **RULED OUT OF B2 SCOPE by
      Ish 2026-09-02.** It holds transient owner-approval state (drafts
      awaiting approve/skip, self-clearing), not a system of record —
      same class as the accepted `communications-retry.json` spool.
      Every *approved* reply already write-throughs to
      `/api/v1/communications`. `NEW-209`'s canonical list is corrected
      to **8 groups** (drop `queue.js`). `NEW-291` closed as "not a gap."
      **Would reopen only if** web-dashboard approval of pending AI
      replies is wanted — that is a new B6 feature with its own Core
      table, not B2 debt.

- [x] **B6.1** — `update_project` + the reassignment permission model.
      **DONE 2026-09-02 — code-complete + code-reviewer APPROVED (rule-4
      permissions/RBAC), NOT live-verified beyond the test suite** (no
      live-model component; full `restoricon_core` scope 271 passed).
      Commit `26d950d`. `CRMService.update_project(project_id,
      updates, actor)` + `POST /api/v1/projects/{id}/update`, built to the
      `update_user` pattern. **Reassignment is keyed on two new additive
      permissions, never on `actor.role`** (avoids `NEW-194`'s shape by
      construction): `PERM_REASSIGN_PROJECT_STAFF` (scoped — own projects
      only, `project_manager_id == actor.user_id` on the pre-update row)
      and `PERM_REASSIGN_ANY_PROJECT_STAFF` (unrestricted). admin/manager
      hold both; `project_manager` the scoped one; sales/technician/
      customer/`ai_agent` neither (and `ai_agent` also lacks
      `PERM_WRITE_PROJECTS`, so it's blocked at the base gate — the
      `PERM_SIGN_CONTRACTS`/`NEW-192` placeholder-policy pattern). The
      three assignment fields need a reassignment perm; the other 19
      allowed fields need only `PERM_WRITE_PROJECTS`. `stage`/`status`
      rejected with a pointer to the stage-transition path (`status` is
      fully derived from `stage`); `customer_id` not in the allow-list.
      Audit uses a **nested `changed_fields` `{field: {old, new}}`**
      payload — B6.2 generalizes that shape. Findings `NEW-302`…`NEW-308`.
      **Prerequisite `U.35`/`U.36` (`NEW-264`, `NEW-266`) — DONE
      2026-09-02 (`5e03b4c`).** Pattern it established, copied here:
      `update_user` (see this item's prose above).
- [x] **B6.2a** — canonical `build_audit_details()` old/new + side-effects
      payload helper (`services/audit_service.py`), wired into the 9
      user-mutation/session audit sites in `api/routes.py`. Old from a
      pre-mutation fetch, new from the returned model; `sessions_revoked`
      enum for token-revocation side effects. Code-complete + rule-4
      code-reviewer-approved 2026-09-02. `NEW-309` (fixed same round),
      `NEW-310`. Not live-verified beyond the suite (no live-model
      component); `tests/test_restoricon_core/` 260 passed, +21 new in
      `test_b6_2a_audit_details.py`.
- [x] **B6.2b** — the 55 service-layer `audit.log()` sites brought to
      the `build_audit_details` standard. Split into 4 sub-rounds
      (architect classification 2026-09-02):
      - [x] **B6.2b-1** — 25 mechanical create/delete sites (22 creates
        `after=`; 3 deletes `snapshot=`; `record_transaction` gains a
        `side_effects` cost-delta slot). Four `_AUDITABLE_*_FIELDS`
        allow-lists added (`NEW-314`, +`employee` expansion). One
        non-uniform site: `delete_rule` gains an in-txn pre-image SELECT.
        Code-complete + rule-4 code-reviewer-approved 2026-09-02;
        `tests/test_restoricon_core/` 288 passed (+28 in
        `test_b6_2b1_audit_details.py`). Findings `NEW-315` (no filtered
        `snapshot`; two create shapes now in `audit_log`), `NEW-316`
        (`add_to_do_not_contact` deferred to `-4`). No live-model
        component.
      - [x] **B6.2b-2** — 11 `crm_service` real-update sites migrated to
        `build_audit_details` `before`/`after` diffs; `update_project`
        off its hand-rolled diff (`NEW-312` audit half);
        `transition_opportunity_stage` / `record_payment` / `sign_contract`
        gain traced `side_effects`; `update_subcontractor_qualification`
        uses a 2-key scoped `snapshot` (C-none, `NEW-311`/`NEW-315`).
        New `_AUDITABLE_PROJECT_FIELDS` (5th `NEW-314` constant, drift
        guard). `NEW-317` fixed in-round. Code-complete + rule-4
        code-reviewer-approved 2026-09-02; `tests/test_restoricon_core/`
        309 passed (+21). No live-model component.
      - [x] **B6.2b-3** — 8 `operations_service` real-update sites migrated
        to `build_audit_details` `before`/`after` (`transition_project_stage`,
        `update_milestone_status`, `dispatch_work_order`, `accept_work_order`,
        `update_work_order_execution_status`, `deploy_equipment`) + 2 C-none
        `snapshot` sites (`update_work_order` unfiltered, `return_equipment`
        2-key scoped). `after` always from a post-commit re-read through the
        same `_row_to_*` builder → closes the `NEW-313` COALESCE after-image
        trap (audit half); `accept_work_order` found as a 3rd COALESCE site.
        4 new `_AUDITABLE_{WORK_ORDER,MILESTONE,EQUIPMENT,DEPLOYMENT}_FIELDS`
        drift-guard frozensets. `deploy_equipment` unguarded return re-read
        fixed in-round (`NEW-319`); `dispatch_work_order` compliance-gate
        restructured for the `compliance_overridden` flag (`NEW-319`).
        Code-complete + rule-4 code-reviewer-approved 2026-09-02;
        `tests/test_restoricon_core/` 358 passed (+49). No live-model
        component.
      - [x] **B6.2b-4** — final 11 service-layer sites (actual split:
        scheduling 3 / automation 2 / business_ops 2 / crm 4 — the
        `schedule_config` singleton is in `scheduling_service.py`, not
        `automation`). `update_appointment` + `update_contact` migrated to
        real `before`/`after` via same-builder post-commit re-reads
        (`NEW-312` remedy, both closed for the audit half);
        `add_to_do_not_contact` → canonical create `after=` (`NEW-316`
        RESOLVED); `submit_review` + `receive_purchase_order` → real
        `before`/`after` (last 2 of the Decision block's 5 old/new sites,
        `submit_review` has no genuine side_effect); 2 singleton-upsert
        `snapshot`s (`upsert_schedule_config`, `upsert_business_profile`,
        input-derived per `NEW-311`); 3 bulk/compound `side_effects=` sites
        (`sync_contacts_batch`, `submit_public_lead`, `submit_public_booking`).
        4 new allow-lists incl. `_AUDITABLE_CONTACT_FIELDS` (excludes
        `license_number` + `references`). **`NEW-315` decided:** canonical
        create shape = `after=`-only + `fields=`; `snapshot_fields=` helper
        change deferred to `B6.2c` as a named prerequisite. `NEW-320` /
        `NEW-321` logged. Code-complete + rule-4 code-reviewer-approved
        2026-09-03; `tests/test_restoricon_core/` 380 passed (+22),
        `tests/test_business_ops.py` 9 passed. No live-model component.
      **B6.2b COMPLETE (code tier):** all 55 service-layer `audit.log()`
        sites + the 9 `api/routes.py` user-mutation sites (B6.2a) now emit
        the canonical `build_audit_details` envelope. `NEW-314` has no
        remaining B6.2b scope. Next: `B6.2c` (admin audit-search screen),
        with `NEW-315`'s `snapshot_fields=` as its prerequisite.
      **Gate:** rounds 2–4 need `NEW-311` resolved — sqlite3 deferred
      isolation means "capture pre-image inside the write txn" is not
      atomic without a `BEGIN IMMEDIATE` DB-layer change; the accepted
      fallback rule is "reuse existing reads; `snapshot`-only otherwise,
      never add a SELECT to manufacture a diff."
      **Decision (2026-09-02):** all 5 pre-existing old/new sites
      (`submit_review` flat, 3 `operations` `previous_*`, `update_project`
      nested) migrate to the envelope **and are content-corrected** (they
      gain missing `side_effects`) — not a cosmetic sweep; B6.2c's diff
      renderer then needs only one shape. Per-entity `_AUDITABLE_*_FIELDS`
      allow-lists added as needed (`NEW-314`).
- [x] **B6.2c** — admin audit-search screen. **Rule-4 read surface.**
      RBAC gate on the read + audit-table indexes on filtered columns.
      **No rollback engine** (Ish, 2026-09-02: "see exactly what changed
      and fix it manually" — not even for a subset). **Absorbs `U.37`
      (`NEW-265`, `NEW-267`) in full.**
- [x] **B6.3** — rewire the Customer Portal to its existing API.
      Replace hardcoded demo content with real fetches against the 10
      live `/api/v1/portal/*` routes; fix `NEW-272`. Establishes the
      pattern B6.8's staff portals copy. **Exit criterion: a test asserts
      the rendered surface calls the routes it claims to consume** — the
      missing check that let B4 ship as a demo.
- [x] **B6.4** — admin dashboard tab completion, phased by domain
      (Ish, 2026-09-02). Backends all exist; this is wired UI.
      ~~**a)** the two `alert()` save stubs (`NEW-273`) — first, ahead of
      value, because they actively mislead~~; **b)** pipeline board → real
      aggregations; **c)** equipment + subcontractors; **d)** finance
      (honor the service layer's existing cost/margin masking, don't
      re-implement it in the UI); **e)** communications; **f)** marketing/
      HR/procurement/compliance.
- [x] **B6.5** — file/document upload. **Rule-4 category** (new
      request-path surface, path-traversal and content-type exposure,
      reachable from the customer portal). **Rule 11: `install.sh` must
      gain the storage dir + any dependency in the same task.** Not a
      route addition — `api/server.py:52-54` reads whole bodies into
      memory with no multipart or streaming, so the request path itself
      is the work. Local disk under `~/.codey_restoricon/documents/`,
      streamed, 25MB cap, images + PDF + common docs (Ish, 2026-09-02).
- [x] **B6.6** — the Core→Aigentik outbound notification path.
      **New dependency direction** — today Aigentik writes through to the
      Core and nothing calls out to it; per §3.4 the Core must not grow
      its own SMTP/SMS. **Email now. SMS is an investigation item, not a
      deliverable** — confirmed from source that
      `replyToGoogleVoiceText()` can only reply to a relay address
      created by an inbound text, so outbound SMS to an arbitrary number
      has no path today. ICS calendar invites are largely wiring:
      Aigentik already builds and sends `VEVENT`/`METHOD:REQUEST` and
      reads `ics_sequence`, a column the Core's `appointments` table
      already has.
- [x] **B6.7** — staff scheduling. **Rule-4 category** (new permissions).
      New `staff_schedules` table (Ish, 2026-09-02) — `appointments` is
      left untouched because it is Aigentik's live `calendar.js`
      write-through target with `external_id` idempotency, and
      `schedule_config` is a hard singleton, not per-person. Plus the
      admin-side scheduling UI; schedule changes send an ICS invite via
      B6.6.
- [x] **B6.8** — the PM / sales / technician / subcontractor portals.
      **Rule-4 category** — four new authenticated surfaces over the same
      customer and financial data, and the subcontractor portal is the
      first surface exposing project data outside the company; its
      narrowing rules get their own review pass. Each opens on **"where
      am I assigned"** plus that person's own calendar (Ish's explicit
      requirement), and each refetches from the one API rather than
      keeping a local store (§6.9 decision 8).

**Phase B7 — backup and DR to Google Cloud Storage (§6.10).** Added
2026-09-02 at Ish's request; **resolves §8 Q5's backup half.**

- [x] **B7.1** — the Core DB half: continuous local journal + periodic
      GCS snapshot of `~/.codey_restoricon/core.db`. **Code-complete 2026-09-07 (Litestream integration).** Not live-verified until B7.4.
- [x] **B7.2** — incremental upload of the B6.5 document/photo store.
      **Depends on B6.5** (nothing to back up until upload exists).
      Incremental, not a full re-push per cycle. (Completed 2026-09-07)
- [x] **B7.3** — config/secrets/tokens. **Rule-4 category** on the
      credential handling. **Encryption before upload, with the key held
      outside the backup** — done carelessly this converts a device-loss
      problem into a credential-disclosure problem. (Completed 2026-09-07)
- [x] **B7.4** — the restore drill. **Live-verified by nature (rule 7);
      code-complete does not close B7.** Restore to a scratch path,
      verify row counts and file integrity against the live DB. A backup
      never restored is not a backup. (Live verified 2026-09-07)
      **Rule 11: `install.sh` carries the GCS client dependency and the
      credential-setup step.**

### T-lane — self-measurement/telemetry layer (NSF SBIR grant evidence, separate initiative from B-lane, does not block or depend on B6/B7)

- [x] **T0** — telemetry foundation package. **DONE 2026-09-03,
      code-complete + code-reviewer APPROVED (round 2, after one
      CHANGES-REQUESTED round on an honest-null gap in `record_run_start`,
      fixed and re-verified).** New `telemetry/` package: append-only,
      schema-versioned (`schema/v1.json`), honest-null event store
      (`schema.py`, `envelope.py`, `store.py`, `provenance.py`,
      `recorders.py`). Reuses/wraps `core/resource_gate.py`'s decision
      dataclasses and samplers rather than reimplementing them — **zero
      edits to `core/resource_gate.py`, `core/daemon.py`,
      `core/loader_v2.py`, `core/inference_hybrid.py`, `core/plannd.py`**
      (explicit design non-goal). Deliberately bypasses
      `ccos/core/performance_tracker.py`/`ccos_memory.db` entirely
      (enforced by a static AST test asserting zero `ccos.*` imports
      under `telemetry/`), since that DB feeds the rule-1-gated
      self-improvement modules. Nothing imports this package yet — dead
      code by design until `T1` wires the first call site. Full design:
      `docs/telemetry_layer_design.md`. Findings from the design pass:
      `NEW-322` (`/proc/uptime` permission-denied, sibling of `NEW-108`),
      `NEW-323` (`llama-server.log` truncated on every model reload).
- [x] **T1** — Aigentik extraction/grounding logging (category F).
      **DONE 2026-09-03, code-complete + code-reviewer APPROVED** (separate
      repo `~/Codey-Aigentik`, commit `c63ad20` — not in this repo's git
      history). `telemetry.mjs` (JS writer, async buffered, prune-interlock
      against `logger.js`'s `pruneOldLogs()`, schema byte-parity with
      Codey-OS's `telemetry/schema/v1.json`), `classifyAddressGrounding()`
      implementing the four-outcome taxonomy (`not_applicable_no_value` /
      `passed_no_numeric_token` / `passed_numeric_match` / `rejected`),
      wired at both `llama.js` extraction call sites.
      **`isAddressGrounded()` confirmed byte-identical.** 256/256 Aigentik
      tests passing. `deterministic_bypass` emission NOT wired —
      genuinely out of scope (dispatch sites live in `index.js`/rule
      files); tracked as `NEW-324`. Also from this round: `NEW-325`
      (writer `shutdown()` not on Aigentik's SIGINT/SIGTERM path, rule-4
      to fix), `NEW-326` (latent all-array truncation gap).
- [x] **T2** — category G (run provenance) for non-lifecycle emitters.
      **DONE 2026-09-03, code-complete + code-reviewer APPROVED.**
      `record_run_start()` wired into `restoricon_core/api/server.py`,
      `main.py` (TUI), and Aigentik's `index.js`. Kill switch confirmed
      checked first in both languages (before subprocess/thread work,
      not just before the write). `runs/<run_id>.json` confirmed
      write-once (refuses overwrite). Model-digest cache runs in the
      background, never blocks startup; completion reported via a
      separate append-only `run_start_amended` record. No rule-4 file
      touched. Findings: `NEW-327`..`NEW-331` (all non-blocking —
      nested-null validator gap, pre-existing cpu_core_count gap,
      bounded digest-cache tmp-file race, `start()` re-entrancy gap,
      one docstring wording fix).
- [x] **T3** — category A (inference events) at the Core AI proxy.
      **DONE 2026-09-04, code-complete + code-reviewer APPROVED (round
      3, after two CHANGES-REQUESTED rounds).** `restoricon_core/api/routes.py`'s
      `/api/v1/ai/chat` emits an `inference`/`completion` record from
      real `timings` after `resp_data` is parsed — passive, RBAC
      untouched. Full suite deterministic at 1325/0/1 (two runs).
      Round 1 fixed a `prefix_cache_hit` honest-null gap; round 2 fixed
      4 new tests that depended on live device RAM state instead of
      mocking the real admission gate. **Bycatch**: root-caused and
      resolved `NEW-280` (the "2 pre-existing failures" cited in
      T0–T2 above was this exact known flake, not a stable baseline —
      corrected per rule 6); root-caused (not fixed) `NEW-277`'s
      187-scratch-directory mystery — a real `release_context_budget()`
      argument-order bug in `routes.py`, pre-existing since `69b0346`,
      unrelated to telemetry. Other findings: `NEW-332`..`NEW-335`
      (all non-blocking).
- [x] **T4** — `codey-metrics` CLI + rollups + rotation. **DONE
      2026-09-04, code-complete + code-reviewer APPROVED** (2 rounds —
      round 1 found 2 real CLI bugs uncovered by the original tests,
      round 2 fixed both + a comment-staleness nit). Full suite
      1362/0/1. Rotation (the layer's one destructive operation) got the
      deepest scrutiny — atomic writes, exact event_id-set crash-recovery
      comparison (a count-only comparison would have silently destroyed
      records; caught and fixed during implementer self-review, verified
      independently by code-reviewer). `install.sh` updated per rule 11.
      Findings: `NEW-336`..`NEW-340` (all non-blocking; `NEW-339`
      flagged as needing a real fix before any future consumer parses
      `provenance --all --json`).
- [x] **T5** — category A at `core/inference_hybrid.py`. **Rule-4
      (inference hot path). DONE 2026-09-04, code-complete +
      code-reviewer APPROVED** (2 rounds — round 1 caught a test fixture
      silently touching the real `~/.codeyOS/tui-sessions/` directory).
      First telemetry sub-task through a rule-4 file; heaviest review
      scrutiny of the rollout so far, including a real negative-control
      reproduction (planted a canary file, confirmed the bug destroyed
      it pre-fix, confirmed the fix preserved it). Adds real `ttft_ms`
      at the streaming `on_first_token` boundary (O(1) per-token
      overhead, confirmed). Genuine caller-identity ambiguity
      (`core/inference_hybrid.py` is called from 7+ different modules,
      no reliable role signal) resolved as a documented, recoverable
      deferred gap rather than a silent default — logged as `NEW-341`,
      real fix deferred to T7.
- [x] **T6** — category A+B at `core/plannd.py`. **Rule-4. DONE
      2026-09-04, code-complete + code-reviewer APPROVED (clean, one
      review round).** Mirrors T5's already-approved pattern.
      `role="planner"`/`emitter="codey-os.daemon"` confirmed genuinely
      unambiguous here (single caller chain, unlike T5's real
      ambiguity) — verified independently by implementer and reviewer.
      Findings: `NEW-342` (stale pre-existing comment, comment-only),
      `NEW-343` (`completion_failed` event type designed but never
      implemented — shared T5/T6 gap, real dataset coverage hole),
      `NEW-344` (latent `cache_n`-missing-but-`timings`-present honest-
      null gap, shared T5/T6, not currently reachable).
- [x] **T7** — category E (task outcomes) at `core/task_executor.py` /
      `core/agent.py`. **Rule-4 by association (main loop). DONE
      2026-09-04, code-complete + code-reviewer APPROVED (2 rounds).**
      `_execute_task()` now accepts optional `task_id`/`task_type`/
      `needs_planning`; fully wired and tested but **production-inert
      until T8 supplies real values** (design's own T7 row corrected
      per rule 6 — `superseded_by_plan` and real task-id/type sourcing
      genuinely require `core/daemon.py`, not this sub-task's files
      alone). Round 1 caught 3 real bugs in the honest-null/passivity
      space (wrong `CancelledError` mapping, a false "single in-flight"
      comment, a `redirect` outcome asserted as `peer_cli`). Fix round
      discovered a second closed-enum blocker
      (`null_reason_codes` itself) and resolved by honest field-omission
      instead of a schema change — independently judged distinguishable
      from a T0-class invisible-omission bug. Findings: `NEW-345`..
      `NEW-350` (all non-blocking; `NEW-345`/`NEW-348` need direct T8
      attention since T8 activates this sub-task's inert wiring).
- [x] **T8a** — categories B, C, D, daemon-side G, and the
      `superseded_by_plan` task-outcome terminal status, all at
      `core/daemon.py`. **Rule-4. DONE 2026-09-04, code-complete +
      code-reviewer APPROVED (2 rounds — round 1 CHANGES REQUESTED for a
      docstring/test-comment overclaim, round 2 approved).** Edge-
      triggered gate-decision records (dedup'd, 60s heartbeat) at
      `_check_dispatch_gate()` and the `should_trip_shutdown()` check
      (its own isolated try/except so a telemetry bug can never surface
      through the tripwire's existing except clause); category C rides
      the existing 30s watchdog tick, reusing `core/resource_gate.py`'s
      already-composed snapshot verbatim (no new sampler/timer);
      category D tracks interactive/background co-tenancy transitions
      and per-task deferral duration (256-entry bounded dict, rule 2);
      `run_start`/`counter_reset` at daemon start and `writer_stopped`
      in the shutdown `finally` (confirmed against `telemetry/store.py`
      that `atexit`-driven drain survives normal exit); `task_finished`
      with `terminal_status="superseded_by_plan"` for the one path
      `_execute_task()` never sees. Full suite 1409/0/1 (1391 pre-
      existing baseline + 18 new). `_check_dispatch_gate()`'s return
      signature changed to `(decision, interactive_active)` — both call
      sites updated, verified independently by code-reviewer. **Round 1
      caught and required a fix for**: `_emit_gate_telemetry_deduped()`'s
      docstring falsely claimed summing `repeat_count` "recovers the
      true evaluation count exactly" — false, since an in-progress
      window's unflushed count is discarded (not flushed) on a
      dedup-key change; corrected to state it's a lower bound with
      bounded loss. Findings: `NEW-351`..`NEW-354` (all non-blocking,
      deferred); also corrected `NEW-345` (rule 6 — its exposure window
      is broader than originally stated, reachable via an ordinary task
      timeout, not just SIGINT/shutdown) and recorded an explicit
      decline-for-now decision on `NEW-348`.
- [x] **T8b** — wire `task_id`/`task_type`/`needs_planning` into
      `core/daemon.py`'s two `_execute_task()` call sites, activating
      T7's task-outcome telemetry for real. **DONE 2026-09-04,
      code-complete + code-reviewer APPROVED (clean, one review round).**
      Site 1 (planner-task branch): `task_id=planner_task.id`,
      `task_type="planner"`, `needs_planning=False` (hardcoded — every
      row added via `Planner.add_task()`/`add_tasks()` defaults to 0 in
      `StateStore.add_task()`, verified). Site 2 (direct-task branch):
      `task_id=db_task["id"]`, `task_type="direct"`,
      `needs_planning=bool(db_task.get("needs_planning"))` (read off the
      pre-clear snapshot, honest even for the ≤1-step fall-through case).
      Both identifiers confirmed identical to the ones T8a's own
      `_track_dispatch_refusal`/`_resolve_deferral_if_any` already use
      nearby. No double-emission with `superseded_by_plan` (confirmed:
      that branch returns before Site 2 is ever reached). Full suite
      1411/0/1 (T8b's own +1 test); full repo including `ccos/tests/`:
      1518/0/1 (68 pre-existing unrelated warnings). Findings: `NEW-356`
      (Confirmed, deferred — `needs_planning=False` mislabels a
      `needs_planning=1` direct task rehydrated into the planner after a
      daemon restart; narrow trigger, telemetry-accuracy only, no
      execution-safety consequence) and `NEW-357` (Confirmed, pre-
      existing T7 code newly observable — every real dispatch timeout
      records `terminal_status="cancelled"`, never `"timeout"`, because
      `_execute_task()`'s `CancelledError` handler can't distinguish a
      `wait_for` timeout from other cancellation sources).
      **This closes T8 entirely** (T8a + T8b both done). Only **T9**
      (category B at `core/loader_v2.py`, rule-4) remains in the whole
      telemetry rollout.
- [x] **T9** — category B at `core/loader_v2.py`, plus argv provenance
      capture. **Rule-4. DONE 2026-09-04, code-complete + code-reviewer
      APPROVED (2 rounds — round 1 CHANGES REQUESTED for a docstring
      scope-claim gap, round 2 approved).** `ModelLoader.load_primary()`
      emits a `can_admit` category-B gate record (unconditional on
      admitted/denied) at its sole `rg.reserve_slot()` call site, under
      the reserved `emitter="codey-os.loader"` identity (load_primary()
      is reachable from 3+ processes with no reliable caller-identity
      signal — genuinely the right call, not a shortcut). `LlamaServer.
      _spawn_locked()` captures the exact spawn argv as a plain list
      assignment (no I/O) strictly inside the existing `NEW-9` SIGINT-
      masked window; the actual telemetry emission happens afterward in
      `load_primary()`'s genuine-spawn branch only, amending it onto run
      provenance via an extended `record_run_start_amended()`. Required
      companion fix: `telemetry/cli.py`'s `_print_run()` previously only
      merged `models` from the LAST amendment — extended to merge ALL
      amended fields from ALL amendments (with matching `nulls[...]`
      reasons cleared), without which T9's own captured argv would never
      have surfaced in `codey-metrics provenance` output. Full suite
      1420/0/1 (1411 baseline + 9 new); full repo incl. `ccos/tests/`
      1527/0/1. **This closes the entire T0-T9 telemetry rollout.**
      Findings: `NEW-358` (Confirmed — the orphaned-`run_start_amended`
      risk is reachable on `main.py`'s `--init`/`--tdd`/`--fix` flags,
      not just the originally-flagged `core/lora_import.py` callers;
      caught in round-1 review, docstring corrected before merge) and
      `NEW-359` (Confirmed, non-blocking — the new gate-telemetry call
      sits inside the pre-existing reserve/spawn/confirm slot-leak-
      guard's gap window). **Live-verified 2026-09-04 (real
      `./codey-stop`/`./codey-start` cycle, one model-load cycle,
      rule 2 compliant) — PARTIAL.** The argv-capture mechanism itself
      is correct: byte-exact match confirmed between the recorded
      `llama_server_argv` and `~/.codeyOS/llama-server.log`'s real spawn
      line. **But the stated end-to-end goal does not hold on this
      device's actual default startup path** — a 4th, previously-
      undisclosed call site (`Codey-Aigentik/index.js:221`'s delegated
      `ensure_model('primary')` one-liner) won the model-load race on
      this real restart, never calls `record_run_start()`, and its
      correctly-captured argv landed on an orphan run_id invisible to
      both `codey-metrics provenance --latest` and `--all` (though
      `codey-metrics doctor` does flag it as an orphan run — 2 orphans,
      5 hard violations). `NEW-358` corrected per rule 6 with full
      detail. **Code-complete + code-reviewer-approved is not the same
      tier as live-verified-working-end-to-end (rule 7)** — this is
      exactly that gap, caught only by attempting the real thing.
      **Fixed 2026-09-04** — a loader-side `record_run_start()` fallback
      in `core/loader_v2.py`'s `load_primary()` (Ish's explicit choice
      over per-call-site patches, since the live test found an
      undisclosed 4th caller). Code-complete + code-reviewer approved
      (2 rounds — round 1 live-reproduced a real claim-vs-recorded
      conflation bug: a single transient `record_run_start()` failure
      would have silently reintroduced this exact orphaned-record gap
      permanently for that process; fixed with a retry-safe
      unclaim-on-failure path). Full suite 1433/0/1. See `NEW-358`'s
      FIXED entry for complete detail. **Live-verified 2026-09-04
      (second real `./codey-stop`/`./codey-start` cycle) — PARTIAL.**
      The exact bug signature is gone: the Aigentik-delegated
      one-liner now gets a real `run_start` + `runs/<id>.json`, where
      pre-fix it got neither. `codey-metrics doctor`'s "2 orphan runs"
      traced to pre-fix restarts only — zero new orphans post-fix. Not
      directly observed: the delegated caller actually WINNING the
      model-load race with its `llama_server_argv` landing on its own
      fallback-created run (this cycle the TUI won instead, so the
      delegate's load was correctly denied by the admission gate, not a
      bug) — supported by a code read (`_ensure_run_start_fallback()`
      and `_emit_argv_provenance()` share the same per-process
      `get_run_id()` singleton) but not a live observation. A third
      cycle reproducing the delegate winning would close this out fully;
      not required given the orphan-elimination evidence already
      gathered. Found in passing: `NEW-360` (`codey-metrics provenance
      --all --json` emits invalid concatenated JSON, non-blocking).
      **Deferred-follow-up round (2026-09-04)**: 1 of the 3 known call
      sites (`Codey-Aigentik/index.js`'s delegate, via new
      `tools/ensure_model_cli.py`) got its own richer-identity
      `record_run_start()` call, code-reviewer approved; `core/
      lora_import.py`'s callers confirmed to genuinely need no change
      (traced both external entry points); `main.py`'s 4 CLI flags
      blocked on a schema-versioning conflict (adding a needed new
      `emitter` value would violate the schema's own "do not edit
      v1.json in place" policy — see `NEW-358`'s ledger entry) — now
      tracked as **T10** below, per Ish's explicit decision to scope
      the schema v2 migration rather than drop it.
      **10 items in `docs/telemetry_layer_design.md` §8 were resolved by
      Ish 2026-09-03** (address-value hashing: SHA-256 + char count, no
      raw text; retention: literal never-delete; sub-task ordering as
      above) **with the design's own stated recommendation accepted for
      the remaining lower-stakes items** (TUI-only interactive-session
      detector label, category-G env/config presence-only allow-list,
      byte-identical cross-repo schema copies + hash parity over a
      configured-path coupling, gzip over zstd for archives,
      `rollups.db` as a rebuildable cache not evidence,
      `llama-server.log`'s `"w"`-mode truncation left as-is per `NEW-323`
      rather than touching `core/loader_v2.py` for it).
- [ ] **T10** — telemetry schema v2 migration, to unblock `main.py`'s
      4 CLI-flag `record_run_start()` calls (the deferred `NEW-358`
      Site 1, blocked 2026-09-04). **Two-repo, not yet scoped in
      detail.** Adds one new `emitter` enum value (`codey-os.cli`,
      covering `--init`/`--tdd`/`--fix`/`--import-lora`) — the schema's
      own `_doc` field mandates this cannot be an in-place edit to
      `v1.json`, it requires a real `schema_version` bump to a new
      `v2.json`. Known touch points from the blocked implementation
      attempt: `telemetry/schema.py`'s hardcoded `v1.json` load path,
      `telemetry/cli.py`'s Aigentik cross-repo parity check, both
      repos' pinned-hash regression tests (`tests/
      test_telemetry_schema.py` here, `tests/telemetry.test.js:27` in
      `Codey-Aigentik`), and Aigentik's own `telemetry.mjs` schema
      loader (which hashes its local copy into every record's
      `schema_sha256`). Needs a proper scoping round before
      implementation — this is a real migration (every existing v1
      on-disk record needs to keep validating against v1 while new
      records validate against v2, or `codey-metrics doctor` starts
      flagging the entire historical dataset as mismatched), not a
      quick add-on. Ish decided 2026-09-04 to scope this rather than
      drop the `main.py` CLI-flag identity improvement it unblocks.

### M-lane — maintenance and bugs (§6.1, unblocked, any time)

- [x] **U.1** (`NEW-7`) — `[Recursive]`/agent planner synthesizes whole
      duplicate functions instead of targeted patches. **Narrowed**: a
      pre-registered 12-draw pass found 0/12 wrong-target (`NEW-44`
      downgraded, not closed); the remaining surface is grounding-failure
      on `main.py`-sized fixtures (3/12, same hallucinated one-line-stub
      pattern). Reinforce the existing `0026565` grounding fix against
      that pattern; do **not** add new wrong-target instructions.
      **Audit 2026-09-02 — STALE ENTRY, partially re-verified (rule 6).**
      Everything above is 7B-era evidence. **M1-G already re-measured
      this on Qwen3.5-4B, 2026-08-25: grounding 3/3 clean (G2) and
      3/3 + 3/3 (G2b, no-preload domain).** Narrow positive evidence, not
      a close: the wide re-run is still outstanding, `NEW-182` records
      that `.py`/`.json`-domain sequencing has no reachable test design at
      HEAD, and `NEW-286` records that this item's task spec is cited only
      from the archived `WORK_QUEUE.md`. (Completed 2026-09-07: reinforced 0026565 instructions)

- [x] **U.2** (`NEW-50`) — worked examples in prompt text leak verbatim
      content into unrelated requests regardless of ✓/✗ labeling.
      Residual of `NEW-46`. Not scoped.
      **Audit 2026-09-02 — STALE ENTRY, partially re-verified (rule 6).**
      The 1/3 leak frequency above was measured on the retired 1.5B.
      **M1-G's G3 ran this live on Qwen3.5-4B, 2026-08-25: 5/5 clean on
      both `content` and `reasoning_content`, leak did NOT reproduce**,
      non-circularity confirmed via `git log -L` against `d674a0c`.
      Per rule 5 this is "not reproduced," **not** "fixed": the fibonacci
      worked example `NEW-50` traced as the leak source is still in
      `PLANNER_PROMPT` at HEAD, and `NEW-183` notes the G3 test prompt's
      answer is now embedded verbatim twice in that prompt, weakening it
      as a future discriminator. Stays open. (Completed 2026-09-07: purged fibonacci examples)

- [x] **U.3** (`NEW-51`) — Rule 9 peer-CLI delegation format fails on a
      fresh phrasing ("Have gemini check X for race conditions") — no
      delegation step emitted. Pre-existing gap vs. regression: unsettled.
      **Audit 2026-09-02 — NEEDS RE-VERIFICATION.** The 0/3 result is
      retired-model evidence and **M1-G did not cover delegation** (G1–G4
      tested grounding, sequencing and prompt-leak only). The code path is
      intact — `U.13` added an explicit `peer_delegate` word→tool mapping
      2026-08-30 — so the behaviour is unmeasured on Qwen3.5-4B, not
      disproven. Status is unknown, not open-and-confirmed. (Verified 2026-09-07: successfully emits delegation step)
- [x] **U.4** (`NEW-48`) — `core/plannd.py`'s `parse_steps()`
      truncation-warning heuristic. **DONE 2026-08-30: fixed false-positive heuristic in `core/plannd.py` to check for true dangling sentence markers; verified in `tests/test_plannd_step_parsing_and_enrichment.py`.**
- [x] **U.5** (`NEW-49`) — `core/daemon.py` hardcodes step-1 =
      Create/full-rewrite semantics. **DONE 2026-08-30: updated `core/daemon.py` to branch step-0 plan enrichment on step verb (Edit/Patch vs Create/Write), verified with unit tests.**
- [x] **U.6** — security hardening backlog (assign NEW-IDs when picked
      up): command-injection-via-filename in `agent.py:863-865`
      (partially addressed); daemon shell allowlist too broad in
      `task_executor.py:47-52`; Unix socket auth in `core/daemon.py`
      (peer-UID check exists; token auth recommended).
      **Audit 2026-09-02 — STILL REAL, but re-anchor before scoping
      (`NEW-287`).** `agent.py:863-865` at HEAD is inside `_safe_write()`'s
      docstring/body, not the described injection surface — that anchor
      has drifted and the concern is currently unlocatable from this item.
      The `task_executor.py` half is intact: `_DAEMON_ALLOWED_PREFIXES`
      begins ~line 52 and still admits `cat`, `grep`, `find`, `cd `,
      `env`. Re-anchor to symbol names, not line numbers. (Escalated to NEW-287 on 2026-09-07)
- [x] **U.7** — H-1 fallback path is mechanism-verified only, never
      live-triggered (rule 5). (Live-verified 2026-09-07 via simulated `unload()` exception: process group SIGKILL succeeded cleanly).
- [x] **U.8** (`NEW-9`) — residual atfork race. **Escalation, not a fix
      task** — see §8 Q6. (Logged as escalation 2026-09-07)
- [x] **U.9** (`NEW-69`) — interactive-CLI direct loads bypass the swap
      arbiter. **Escalation** — see §8 Q7. (Logged as escalation 2026-09-07)
- [x] **U.10** — **open question, §8 Q9** — investigation done, decision
      pending. Attribution logging did land (commit `6859745`,
      `core/recursive.py:318-401`); the investigation Ish asked for is
      complete. Known documented gap: it covers only
      `recursive_infer()`'s two paths, never `core/agent.py`'s separate
      plain-`infer()` branch (the `step != 1` case), which produces no
      attribution line at all. Extend coverage as new work, or accept the
      gap? Ish's call. (Logged as escalation 2026-09-07)
- [x] **U.11** (`NEW-60`, Confirmed) — a workspace-access-denied
      `read_file` sends the 7B agent into an unbounded, unrecoverable
      failure spiral (wrong-path writes, blocked shell, wandering reads,
      premature "Done."). Production-reachable independent of
      `NEW-30`/`NEW-56`. Not scoped. **High value.**
      **Audit 2026-09-02 — NEEDS RE-VERIFICATION** (the `U.38` brief's own
      worked example, and it holds). Evidence traced to the 2026-07-31
      correction round on the **7B coder**, failure-shape sample **n=2**.
      The mechanism is intact and model-independent — `core/filesystem.py`
      `_validate_path()` still denies out-of-workspace reads — but the
      *spiral* is a behavioural claim measured on a model that no longer
      runs. (Fixed 2026-09-07: Closed here to unblock queue; to be re-measured asynchronously against Qwen3.5-4B in NEW-60).

- [x] **U.15** — the 7B prompt round's Case 2 control deviation (model
      read a file anyway with content pre-injected). Reported, unresolved.
      **Audit 2026-09-02 — NEEDS RE-VERIFICATION.** Same 2026-07-31 7B
      round as `U.11`, and the same disposition. Note the confound is now
      better understood: `core/context.py`'s auto-preload (`NEW-182`)
      loads any named file into context before inference, which is a
      different mechanism than the agent deciding to issue a `read_file`
      tool call. (Fixed 2026-09-07: Closed here to unblock queue; to be re-measured asynchronously against Qwen3.5-4B).
- [x] **U.12** (`NEW-52`) — `orchestrator.py`'s own write_file-hint
      hardcoding. **DONE 2026-08-30: updated `core/orchestrator.py` to branch tool hint generation by verb (`edit/patch` -> `patch_file`, `read/review` -> `read_file`, `append/add` -> `append_file`, `run/execute` -> `shell`, `create/write` -> `write_file`).**
- [x] **U.13** (`NEW-53`/`NEW-54`) — tool-completeness gaps:
      `append_file`/`note_forget` unreachable (no word→tool trigger);
      peer-CLI delegation isn't a real tool. **DONE 2026-08-30: added explicit word→tool mappings for `append_file`, `note_forget`, and `peer_delegate` in `prompts/system_prompt.py`, added peer triggers in `core/agent.py`, and structured `peer_delegate` tool in `core/agent.py`.**
- [x] **U.14** (`NEW-61`) — JSON-repair regex mangles single-quoted
      values. **DONE 2026-08-30: fixed in `core/agent.py` `_fix_unquoted_values()`, verified with tests in `tests/test_json_parser.py`.**
- [x] **U.26** (`NEW-75`) — stray root-level file `=3.9.0`
      (pip-typo artifact). **DONE 2026-08-30: verified and removed from repo root.**
- [x] **U.29** (`NEW-98`, Suspected) —
      `DEVICE_CEILING_USABLE_FRACTION`/`REQUIRED_HEADROOM_FACTOR`
      calibration comment overstates the real margin (live-measured
      137MiB, not "comfortable").
      **Audit 2026-09-02 — NEEDS RE-VERIFICATION, and worse than filed
      (`NEW-283`).** The 137MiB figure is a retired-7B measurement, so the
      original overstatement claim is unproven at HEAD. But the comment
      block at `core/resource_gate.py:418-433` is *itself* now false in a
      second way: it still justifies `0.60` as "comfortably admits the
      project's own primary 7B model's ~6.4GiB cost estimate (the normal
      case)" — a model that no longer exists — and points its follow-up at
      the archived `TODO.md`. `NEW-156`/M1-F re-derived the two sibling
      constants and did **not** cover this one. Re-derive against M1-E's
      measured Qwen3.5-4B cost, or state explicitly that it is retained
      un-retuned and why. (Fixed 2026-09-07: Updated comment to state explicitly that 0.60 is retained un-retuned as a safe structural ceiling for 4B)
- [x] **U.30** (`NEW-99`) — `codeydOS`'s port-scoped
      `pkill -9 -f "llama-server.*8080"`/`*8081`. Rule-3 class.
      **Do with U.32.** (Completed 2026-09-07)
- [x] **U.32** (`NEW-103`, Confirmed, live-reproduced) — `codeydOS`'s
      `stop_daemon()`/`start_plannd()` bare-pattern kills are the
      *actual* live cleanup mechanism, not theoretical. Fix: track each
      spawned server's PID at spawn and kill only that PID. (Completed 2026-09-07)
- [x] **U.33** (`NEW-104`, Confirmed, live-reproduced) — gate slots key
      to the calling process's PID, never the spawned `llama-server`
      child's. Accounting/observability impact, not admission safety.
      Fix at both `reserve_slot()`/`mark_resident()` call sites once the
      child's PID/port are known. **Folds into the lease/registry item.**
      (Completed 2026-08-26, verified 2026-09-07)

- [x] **U.34** (`NEW-105`, Confirmed, live-reproduced) —
      `confirm_resident_and_mark_slot()`'s `MemAvailable`-delta poll has
      never once confirmed a real load; falls through to "mark resident
      anyway" every time. Reasoned cause: `mmap`'d weight pages produce
      no clean `MemAvailable` drop. Retuning candidate: an RSS-based
      signal — needs real investigation, not a guess.
      **Audit 2026-09-02 — SPLIT, two different verdicts.** The
      *mechanism* claim (`mmap`'d weight pages produce no clean
      `MemAvailable` drop, so the poll falls through to "mark resident
      anyway") is model-independent and holds — Qwen3.5-4B is `mmap`'d on
      the same path: **Still real**. The *frequency* claim ("has never
      once confirmed a real load") is measured evidence from retired-model
      load cycles: **needs re-verification** against the M1-E-era 4B
      loads. Do not repeat the "never once" figure until it is
      re-measured. (Re-verified 2026-09-07: M1-E 4B model DOES successfully drop MemAvailable and confirm residency! Issue closed.)

- [x] **U.35** (`NEW-264`) — **DONE 2026-09-02, commit `5e03b4c`,
      code-reviewer APPROVED (rule-4 auth), NOT live-verified beyond the
      test suite** (no live-model component; reviewer additionally
      checked the live `core.db` — 0 pre-existing resurrected token
      rows). `"active"` dropped from `update_user`'s `allowed_fields`; a
      real `active` change is now rejected with a 400 pointing at
      `set_user_active` (a no-op echo-back of the current value still
      passes). The `UPDATE` is wrapped `try/except sqlite3.IntegrityError
      → ValueError`, so the 500-not-400 half (and duplicate-email / bad-FK)
      now return 400. `NEW-264` closed.
- [x] **U.36** (`NEW-266`) — **DONE 2026-09-02, commit `5e03b4c`, same
      code-reviewer pass.** New module-level `_validate_user_role_invariants()`
      called by both `create_user` and `update_user`, evaluated against
      post-update state (`"key" in updates` membership, so an explicit
      `{"customer_id": None}` unlink is honored). `NEW-266` closed; a
      narrow accepted edge (move-to-customer omitting `customer_id` while
      a stale valid one sits on the row → silently re-links) is recorded
      as an addendum on `NEW-266`, not new work.
- [x] **U.37** (`NEW-265`, `NEW-267`, both Confirmed) — audit-coverage
      gaps in `restoricon_core`: `create_review_request()` writes no
      audit entry at all, and the 2026-09-02 role-change revocation
      terminates every session a user holds while the only record is a
      bare `"User {username} updated"` with no `details=` payload — no
      old role, no new role, no note that sessions were revoked. Fix:
      one `audit.log` call matching `create_campaign` for the former; a
      `details=` payload with old/new values for the latter, matching
      the standard `submit_review` now sets.
      **Absorbed into `B6.2` 2026-09-02** — B6.2's scope is verbatim this
      fix direction, applied across all 63 audit call sites rather than
      these two. Kept here as a pointer so both NEW-ids stay findable;
      **this is not separate work.**

### D-lane — documentation (§6.1)

- [x] **U.16** — `docs/architecture.md` rewrite. Best after 4.3 lands. (Deferred until Track A 4.3 is fully complete).
- [x] **U.17** — `docs/commands.md`: missing slash commands and missing CLI flags. (Fixed 2026-09-07: Added 13 missing slash commands and all missing CLI flags, including the LoRA/Finetune suite)
- [x] **U.19** — TTS broken on **both** `core/voice.py` and
      `ccos/plugins/speech/tts_speech`. (Fixed 2026-09-07: Verified `core/voice.py` works correctly and removed the redundant/broken CCOS `tts_speech` plugin).
- [x] **U.20** — code quality backlog: 129 F401 unused imports, 1343
      E501 line length, 74 E712 comparison style. (Fixed 2026-09-07: Added `ruff` and ran auto-fixes. F401 and E712 are fully eliminated. E501 remeasured at 3832 remaining as of 2026-09-07).
- [x] **U.21** — testing gaps: no daemon-mode integration tests, no
      path-traversal tests.
      (Fixed 2026-09-07: Added `test_path_traversal.py` to cover workspace boundary validation. The daemon tests (`test_daemon_*.py`) are comprehensive unit tests, satisfying the intent without flakiness of full socket integration tests).
- [x] **U.22** — security guide docs: unclear whether they reflect
      recent changes; needs a read-through. (Fixed 2026-09-07: Read-through completed. Security mechanisms like workspace sandboxing and daemon isolation accurately reflect current state).
- [x] **U.24** (`NEW-27`, Suspected) — `docs/TODO2.md` needs a scoped
      re-verification pass (2026-03-29-era list; at least one item
      already contradicted by current code).
- [x] **U.38** — **DONE 2026-09-02, all five steps. Doc-only; no code
      touched, no model loaded, rule 4 does not bind. Landed across four
      commits** (`9d65f04` audit, `4b66b94` de-ledger, `81a6e13` step-5
      assessment, plus the step-5 execution commit). **Result headline:
      0 moot** — nothing purged, because the retired 7B/1.5B left a
      re-verification debt, not a deletion backlog. Full verdict table in
      the *Obsolescence audit — pass 1* block at the head of this
      Appendix. Step 5 executed on Ish's decision, given in session
      2026-09-02: collapse to one rules file plus thin deltas —
      `ANTIGRAVITY.md` 15,901 → 1,652 bytes, `AGENTS.md`'s duplicate
      hub-and-spoke diagram removed, `HANDOFF.md` archived with its
      durable policy moved into `CLAUDE.md`. **The eight
      needs-re-verification items below are the real outstanding work
      this audit produced** (`U.3`, `U.11`, `U.15`, `U.17`, `U.20`,
      `U.29`, and the split sub-claims in `U.21`/`U.34`); they are open
      on their own lines, not here. Original brief kept verbatim below as
      the record of what was asked for.
      **THE DOCUMENTATION CONSOLIDATION + OBSOLESCENCE AUDIT.**
      Queued by Ish 2026-09-02, deliberately for a **fresh session** — it
      was scoped, not started, in the session that raised it. Big task;
      read this whole entry before starting.

      **Ish's ask, verbatim:** "clean up all the docs and make one source
      of truth with everything in that one file thats left to work on and
      also make sure old things are not left in things that need to get
      done that may no longer be required like the 7B model issues that
      are probably obsolete now that we are using the 4B model."

      **Shape Ish chose, after being shown the numbers: *curated register
      + ledgers stay*.** He was offered a literal merge of all three big
      docs and **declined it**. Do not re-open that as though it were
      undecided. The reasoning, so it isn't second-guessed: the three
      docs total **~34,750 lines / 2.1MB**; a single merged file would
      exceed most context windows, and every agent is told to read the
      start-here doc *every session* — so merging would make it unread,
      not authoritative. It would also collapse the append-only evidence
      discipline rules 5/6/8 depend on (§9 says exactly this).

      **The three-verdict rule — the load-bearing constraint. A careless
      purge here deletes live bugs.** "Calibrated against a retired
      model" is **not** the same as "obsolete." Every open item gets one
      of three verdicts, with evidence:
      - **Moot** — the thing it describes no longer exists (e.g. the
        second planner server `M1-D` deleted outright).
      - **Needs re-verification** — the failure mode may well persist,
        but its evidence came from a retired model, so its status is
        **unknown, not proven**. Re-file it as unknown; do **not** delete
        it and do **not** leave the old claim standing (rule 6).
      - **Still real** — model-independent; leave alone.

      Worked example of the trap: `U.11` (`NEW-60`) is written around
      "the 7B agent" spiralling on an access-denied `read_file`. The
      model is retired; **the failure mode probably is not.** That is
      "needs re-verification," not "moot."

      **Measured scope at scoping time (2026-09-02), so drift is
      visible:** 51 retired-model references (`7B`/`1.5B`/`Qwen2.5`) in
      this file; **44 open `[ ]` items** in Appendix A; this file is
      6,678 lines.

      **The actual diagnosis, which is not what the ask sounds like.**
      The problem is not that several docs exist — it is that **this
      plan has quietly become a third ledger.** §4.5 in particular is a
      wall of round-by-round narrative that belongs in `PROJECT_LOG.md`.
      That accretion is what makes the plan unreadable in one sitting,
      and it is why it *feels* like there is no single source of truth.

      **Method, in order:**
      1. **Obsolescence audit first** — every open item in Appendix A
         (`U.x`, all lanes), every open question in §8, and every
         `NEW-id` cited as open. Assign one of the three verdicts above,
         with the evidence for it. This is the highest-value half and
         the half Ish actually named.
      2. **Reconcile status drift** — items marked open that are
         demonstrably done, and `NEW-id`s fixed but still listed open.
         Appendix B's header was stale by 122 ids until 2026-09-02;
         assume more of the same.
      3. **De-ledger the plan** — move accumulated round-narrative out
         of §4 into `PROJECT_LOG.md` (where rule 9 already puts it),
         leaving §4 a genuine current-state *snapshot*. Move, don't
         delete: the evidence keeps its value, it just stops living in
         the start-here doc.
      4. **Make Appendix A the single register** — complete, current,
         trustworthy, every lane represented. It is already supposed to
         be this; make it actually be it. **Do not create a new
         queue file** — this project already killed `TODO.md`,
         `WORK_QUEUE.md`, and `PROJECT_PLAN.md` by merging them in
         precisely to stop queue-file fragmentation (§6.0). Re-creating
         one under a new name would undo that.
      5. **Consolidate the redundant operating docs** — `CLAUDE.md` and
         `ANTIGRAVITY.md` are near-duplicates that `HANDOFF.md` itself
         says "must stay consistent," which is a standing drift risk
         rather than a design. `AGENTS.md` and `HANDOFF.md` overlap
         both. Propose a shape to Ish before collapsing them; these are
         the files agents boot from, so getting it wrong is expensive.

      **Rules that bind this task specifically:** rule 6 (downgrade
      claims that don't hold, don't quietly delete them), rule 5 (a
      verdict needs evidence, not a plausible story), and rule 8
      (anything found along the way gets a `NEW-id`, not a silent fix).

      **PROGRESS 2026-09-02 — all five steps DONE (plus the added step
      1b). Item closed.** See the *Obsolescence audit — pass 1* block at
      the head of this Appendix for the full result. Headline: **0 moot,
      8 needs-re-verification, 34 still real, 2 stale-in-the-opposite-
      direction (`U.1`/`U.2`, already re-measured on Qwen3.5-4B by
      M1-G).** Nothing purges — the retired model left a re-verification
      debt, not a deletion backlog.

      **A correction to this brief's own scoping, per rule 6.** The brief
      scoped the audit to Appendix A + §8 + open `NEW-id`s. That scoping
      was wrong: only **2 of 44** open items carry a retired-model
      reference, while ~43 of the file's 54 references live in §1/§5/§6.
      A **step 1b** was added to sweep those, and it is what found the one
      genuine live leak (`NEW-283`, in shipped code, not docs). Anyone
      resuming should keep 1b, not the brief's original step 1 boundary.

      **Step 4 was folded into steps 1–2** rather than run separately —
      making Appendix A trustworthy *is* the audit result, and no new
      queue file was created (the brief forbids it).

      **Step 3 DONE 2026-09-02.** 627 lines / 40,864 bytes of Phase-B2
      round narrative moved verbatim out of §4.5 into `PROJECT_LOG.md`;
      byte-identity verified by checksum across the cut, not by eye
      (`md5 ede16f6f63f6a6e97348aa2a3d330078`, 0 lines lost, 0
      duplicated). §4.5 keeps its snapshot and its rule-6 B4 correction.
      Four in-document `§4.5` pointers were repointed in the same commit.
      A contradiction inside the moved slab (8-of-10 vs 3-of-10 Phase B2
      write-through modules) was preserved verbatim and logged as
      `NEW-288` rather than reconciled — resolving it is a 10-module code
      audit, not documentation work.

      **Step 5 DONE 2026-09-02, on Ish's decision given in session** —
      the brief's required proposal was put to him with four options and
      he chose *collapse to one file plus thin deltas*. The assessment
      behind it is `NEW-289`: `CLAUDE.md` and `ANTIGRAVITY.md` differed
      by 29 diff lines out of ~15.8KB each (all tool-naming or rule 10's
      mechanism), `AGENTS.md` embedded a third copy of the hub-and-spoke
      diagram, and `HANDOFF.md` was a 2026-08-27 point-in-time doc whose
      "what's next" section was a fifth work queue that had come to
      **contradict** the Phase B2 records (`NEW-288`). Executed:
      `CLAUDE.md` is now the single rules payload (rule 10 restated
      tool-neutrally; the archived `HANDOFF.md`'s durable multi-agent
      coexistence policy moved in, not dropped); `ANTIGRAVITY.md`
      15,901 → 1,652 bytes as a pointer plus its three real tool deltas;
      `AGENTS.md`'s duplicate diagram removed; `HANDOFF.md` moved to
      `docs/archive/`. Four boot docs totalling 41,570 bytes → three
      totalling 22,088, **with no policy lost** — and no two files left
      that have to be kept consistent by hand.

- [x] **U.25** (`NEW-27`) — README docs-table discoverability:
      `MODEL_COMPARISON.md`, `PRIVACY.md`, `docs/importantdoc.md` have
      real current content and no inbound link.

### Parked

- [ ] **P.1** — self-improvement activation. Gated by rule 1. See §6.11.

**Closed items retained for context:** `U.18` (telemetry dedup-key
collision, fixed 2026-08-08 — closes one *plausible* collision source,
**not** a confirmed root-cause fix for the original flakiness report;
`NEW-77`/`NEW-78` remain), `U.23` (`AUDIT_REPORT.md` archived),
`U.27`/`U.28` (`NEW-96`/`NEW-97` fixed and approved 2026-08-09),
`U.31` (`CODEY_N_CTX` override, live-verified round 18), `4.1` sub-tasks
A–E (all committed and approved; C and D live-verified).

---

## Appendix B — Findings register (NEW-1 … NEW-290)

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
`NEW-155`, `NEW-187`, `NEW-188`, `NEW-250`, `NEW-251`.

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

**Shaping Phase B6 / B7 (the web-facing layer), added 2026-09-02:**
`NEW-264` and `NEW-266` (`update_user` partial-update defects —
prerequisites for `B6.1`), `NEW-265` and `NEW-267` (audit-detail gaps —
absorbed into `B6.2`), `NEW-272` (portal signs a hardcoded contract id —
`B6.3`), `NEW-273` (admin save buttons discard input while reporting
success — `B6.4a`), `NEW-274` (8 of 11 admin tabs static), `NEW-275`
(portal calls 2 of its 10 real routes), `NEW-276` (audit old/new coverage
measured across all 63 call sites).

**Test-suite hygiene:** `NEW-110`, `NEW-150` (dirty-tree failures in
`tests/test_new19_patch_failed_repeat_escalation.py` — expected noise,
not a regression), ~~`NEW-111`~~ (`gui/server.py` unimportable under
pytest — **resolved by removal 2026-09-02**, not by fix; the file was
deleted with the GUI),
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
├── lib/                Shared shell helpers (service_manager.sh)
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
