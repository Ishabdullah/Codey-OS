# Codey-OS — Master Vision & Specification

**Status: DRAFT — awaiting Ish's sign-off.**
Once approved, this document becomes the canonical reference. Nothing in
future prompts, restructuring, or code should conflict with it. Any change
to this document after sign-off gets logged in PROJECT_LOG.md as a
deliberate revision, not made silently.

Everything in this document is built from code we've actually inspected,
compiled, run, or tested — not aspiration. Where something is uncertain,
it's marked as such rather than asserted.

---

## 1. What Codey-OS Is

**Naming note:** the project is Codey-OS; day-to-day it's referred to
simply as **Codey**.

A local-first, self-hosted AI agent operating system that runs entirely on
Android via Termux (or any Linux system). It starts from a fully-capable
AI coding agent — everything Codey-OS already does — and wraps it inside
an operating-system shell (CCOS) that can register, run, monitor, and
eventually extend capabilities beyond coding. No cloud dependency required;
optional cloud fallback (OpenRouter) available. Started and stopped as one
unified system via `codey-start` / `codey-stop` (Section 6a), with a TUI
and GUI that can run simultaneously and always show the same live system
state.

**Confirmed direction (Ish, 2026-08-05):** Codey-OS's product scope is a
**multi-agent platform**, not a single coding-agent product — the coding
agent is the first and most mature domain agent, not the whole system.
See Section 9 for the full, dated amendment; this is a deliberate,
explicit, logged scope expansion, not an inference.

**The core relationship:** the OS shell doesn't replace the coding agent —
it governs and exposes it. Every real thing Codey can already do becomes a
registered *capability* the OS shell can discover, route to, monitor, and
(eventually, deliberately) improve.

---

## 2. Architecture — Two Layers

### Layer A: OS Shell (from CCOS)
Owns discovery, routing, safety, and self-knowledge. Does not itself
contain coding-agent intelligence.

| Component | Job |
|---|---|
| `capability_registry` | Central inventory of everything the system can do — tracks name, implementation, dependencies, status, version, performance |
| `plugin_manager` | Discovers, loads, and validates plugins from disk (`plugins/<category>/<name>/`); dynamic loading via `importlib` |
| `tool_router` | Selects the best available tool/capability for a given task |
| `agent_orchestrator` | Internal 5-agent deliberation (Planner, Critic, Optimizer, Capability, Safety) before acting; weighted voting; **Safety Agent can veto any plan** |
| `sandbox` | Isolated execution environment — enforces no destructive commands, no path escapes, resource limits, timeouts |
| `device_manager` | One-time hardware inventory (CPU, RAM, GPU, cameras, mic, storage, network) — gates which capabilities can run on this device |
| `lifecycle_manager` | Top-level pipeline: task → plan → execute → evaluate → improve → register → store |
| `ccos_memory` | OS-level bookkeeping — skills, workflows, configs, event log, performance/telemetry (separate from the coding agent's own conversation memory) |
| `reflection_engine` / `performance_tracker` / `telemetry_engine` | Post-task evaluation, metrics, real-world drift detection, system health scoring |
| `goal_engine` / `project_engine` | Generates and prioritizes improvement goals; converts high-value goals into persistent, resumable, multi-session projects |
| `capability_optimizer` / `skill_recombiner` / `auto_improvement_loop` | Self-improvement mechanisms — **present in the codebase, but gated off from live execution until explicitly activated (see Section 5)** |

### Layer B: Capabilities (from Codey-OS's coding agent, wrapped as plugins)
The actual work Codey does. Each becomes a capability registered with the
OS shell rather than a directly-called module.

---

## 3. Full Capability List (when finished)

Everything below is verified to exist as real, working code in Codey-OS.
"Layer" = where it lives once unification is done. "Status" = whether it's
already wired to the OS shell or still needs wrapping.

| Capability | What it does | Backing code | Status |
|---|---|---|---|
| **Coding agent (core intelligence)** | Reads/writes/edits files, executes tool calls, reasons over a codebase | `core/agent.py`, three-model llama.cpp stack (7B agent / 0.5B planner / embedding encoder) | Needs wrapping as the primary capability — see Section 7.6 step 3 for the fuller plan (must also unify its two existing divergent call paths, not just add a wrapper) |
| **Plan-then-execute mode** | Model writes a numbered plan, user approves, then executes | `core/planner.py`, `core/orchestrator.py` | Needs wrapping (or exposed as a step type inside CCOS's own planner) |
| **Five-tier memory** | Working/project/long-term/episodic/symbolic-graph memory for coding context | `core/memory_v2.py`, `core/symbolic_graph.py`, `core/embeddings.py` | Stays as the coding capability's own memory; separate from `ccos_memory` |
| **RAG retrieval** | Searches local knowledge base, injects relevant docs into context | `core/retrieval.py`, `tools/kb_semantic.py` | Already proven wrappable — was registered as a service in the v4 experiment; template exists |
| **Persistent daemon** | Background process, state survives restarts, task queue | `core/daemon.py`, `core/task_executor.py`, `core/taskqueue.py` | Needs wrapping |
| **Recursive self-refinement** | Draft → critique → refine cycle before code hits disk | Inside `core/agent.py` / `core/recursive.py` | Needs wrapping |
| **Error recovery / strategy switching** | Adaptive fallback when a tool fails (write→patch, import error→pip install, file-not-found→search, test failure→isolate and re-run) with confidence-based, history-adapting strategy selection | `core/recovery.py` — fully implemented, verified complete (classification, fallback trees, real recovery actions, success-rate tracking) | **Complete but disconnected** — needs one thing: a call site in `agent.py`'s tool-failure path. Treat as "wire up," not "build." |
| **Self-status introspection (`/status`)** | Reports token usage, memory status, task queue depth, active model, temperature/context size, process CPU/memory usage, daemon uptime/PID, rolled-up health | `core/observability.py` — fully implemented, verified complete | **Complete but disconnected** — needs a `/status` CLI handler wired to call it. Treat as "wire up," not "build." |
| **Learning / preference tracking** | Tracks user corrections and preferences, error-pattern learning over time | `core/learning.py`, `core/strategy_tracker.py`, `core/error_database.py` | Already active (imported by `agent.py`). **Resolved 2026-07-30:** `strategy_tracker.py`'s overlap with `recovery.py`'s own built-in success-rate tracking was already handled in Phase 2 (`ccos/plugins/coding/error_recovery/error_recovery.py`, commit `0132e0f`) — that plugin routes outcome tracking through `strategy_tracker.py` (the persisted, already-live path) rather than `recovery.py`'s own in-memory one; `recovery.py` itself is untouched. No duplicate tracking in practice. |
| **Git integration** | Branch management, AI commit messages, conflict detection | `core/githelper.py` | Needs wrapping |
| **Voice interface** | TTS output / STT input via Termux:API | `core/voice.py` | Needs wrapping |
| **Static analysis** | Auto-lint on write, `/review` command | `core/linter.py` | Needs wrapping |
| **Thermal-aware inference throttling** | Monitors CPU/battery, reduces model threads under stress | `core/thermal.py`, `core/sysmon.py` | Needs wrapping; complements (doesn't compete with) `device_manager`'s one-time hardware inventory |
| **Fine-tuning export** | Export interaction history, train a personalized LoRA adapter on Colab/Kaggle | `core/finetune_prep.py`, `core/lora_import.py`, `pipeline/` (full training data pipeline) | Needs wrapping |
| **Peer CLI escalation** | Delegates to Claude Code / Qwen CLI / Gemini CLI when stuck, with explicit user consent | `core/peer_cli.py`, `core/peer_shell.py` | Needs wrapping |
| **Unified system dashboard** | Surfaces everything the system has instrumentation for — CPU/thermal status, RAM, storage, battery, what platform/hardware Codey is running on, what capabilities are available vs. active, daemon health — shown in **both** the GUI and the TUI simultaneously | `core/observability.py` (status/health), `core/sysmon.py` + `core/thermal.py` (live resource/thermal state), `ccos/core/device_manager.py` (hardware inventory), `ccos/core/capability_registry.py` (what's available/working) | New requirement — needs a shared data layer both interfaces pull from, so GUI and TUI never show different numbers |
| **GUI** | Browser-based interface, WebSocket-driven, shows the same live dashboard data as the TUI | `gui/server.py`, `gui/index.html` | Existing entry point; extended per the dashboard requirement above, re-homed under `codey-start` (see Section 6a) |
| **OpenRouter cloud fallback** | Optional cloud inference when local models aren't wanted/available | `core/inference_openrouter.py`, `core/inference_hybrid.py` | Stays as a backend option under the coding capability |

**Already-built OS-shell-native capabilities** (no wrapping needed, already CCOS plugins):
- `system_info` — system/process info
- `camera_capture` — device camera capture
- `tts_speech` — text-to-speech
- Auto-generated compound skills: `skill.info_processes`, `skill.camera_capture_tts`, `skill.info_info`

**Known issue — TTS is broken on both sides.** `core/voice.py` and CCOS's
`ccos/plugins/speech/tts_speech` both implement TTS, and per Ish, **neither
currently works.** This isn't a "pick the better one" decision — it's "get
one working, verify it, then remove the other." Deferred until the
wiring/testing phase; not a blocker for sign-off. `core/voice.py` also
covers STT (voice input), which `tts_speech` does not — so even after
picking a TTS winner, STT capability still needs `core/voice.py` or
equivalent, wrapped in.

---

## 6a. Unified Entry Points — `codey-start` / `codey-stop`

**New requirement.** Going forward, Codey-OS (referred to simply as
**Codey** from here) is started and stopped as one thing, not several
separate scripts:

- **`codey-start`** — brings up the full system in one command: the
  daemon/OS shell, the TUI, and the GUI, all running together. TUI and GUI
  are not alternate/exclusive modes — both can be active at once, and both
  display the same live system state (see the dashboard requirement above)
  so a user glancing at either gets the same picture.
- **`codey-stop`** — cleanly shuts everything down: daemon, TUI, GUI, and
  any background model servers.

This replaces the current fragmented entry points (`codey3`, `codeyd3`)
as the primary way to run the system. Those underlying pieces don't
disappear — `codey-start` orchestrates them — but the user-facing surface
becomes these two commands. This also resolves the earlier open question
about the duplicate no-extension `codey3`/`codeyd3` files found in the
repo audit: those get retired in favor of this unified pair rather than
resolved as standalone duplicates.

Two other scripts that were never actually part of the live
orchestration path were subsequently removed as dead/duplicate code,
rather than kept around as unused legacy files: `ccos_main.py`, an
orphaned standalone MVP demo script that nothing in the current codebase
executed or imported; and `gui/start.sh`, a GUI-launch wrapper whose
"start the GUI server, track its PID, tear it down on exit" pattern was
independently reimplemented inside `codey-start` and `codeyOS` rather
than ever being called by either.

---

---

## 4. Governance & Safety Model

- **Sandbox-first execution.** All generated code, plugin installs, and
  plugin tests run isolated before touching the real system.
- **Safety Agent veto.** Highest voting weight (1.5) in the 5-agent
  deliberation; can block any plan. Checks for blocked commands,
  destructive operations, system directory modifications, unsandboxed
  execution attempts.
- **Core invariants (non-negotiable, carried from CCOS's original design):**
  no uncontrolled system modification, no auto-deleting files, no modifying
  the OS shell's own runtime directly, all new abilities go through the
  plugin system, all plugins pass tests before activation, rollback
  available for every plugin install, old plugin versions never deleted.
- **Explicit consent for external sharing.** Peer CLI escalation requires
  user consent before any file contents leave the device.

---

## 5. Self-Improvement — Present, But Gated

The mechanisms for autonomous self-improvement already exist and are
tested (`capability_optimizer`, `skill_recombiner`, `goal_engine`,
`auto_improvement_loop`). **They are not wired into the live execution
path by default.** Activation requires:
- Phases 1–3 of the unification (below) proven stable
- A period of observed, real-task operation through the sandbox/safety-veto
  path
- Explicit sign-off from Ish on activation criteria — at minimum, deciding
  whether goal-engine-generated goals and skill-recombiner-generated
  compound skills require human approval before being registered, at least
  initially

This is a deliberate, reviewable gate — not a technical limitation to
route around later without a decision.

---

## 6. What Codey-OS Is NOT (explicit non-goals, to prevent scope creep)

- Not a cloud service — local-first is a hard requirement, cloud is opt-in
  fallback only.
- Not going to silently drop working functionality during unification —
  every capability in Section 3 must end up wrapped and working, or its
  removal must be an explicit, logged decision with a reason, not a
  byproduct of restructuring.
- Not activating autonomous self-modification by default — see Section 5.
- Not going to let the GUI and TUI drift out of sync — both must read from
  the same underlying dashboard data layer (Section 3's "Unified system
  dashboard"), not maintain separate/duplicate status logic that could show
  different numbers for the same thing.
- Not going back to fragmented entry points once `codey-start`/`codey-stop`
  exist — see Section 6a.
- Not going to duplicate effort by maintaining two implementations of the
  same job (e.g. two planners, two memory systems) without a stated reason
  — where two systems turn out to be genuinely complementary (different
  layers, not true duplicates), that gets documented explicitly rather than
  left ambiguous.
- Not treating Section 7 (dynamic model-tier routing & cross-plugin
  orchestration) as already built. It's planned architecture for future
  rounds, not current behavior — any restructuring step must not describe
  it, or code toward it, as if it already exists.
- Not building a general shared-memory grant across capability domains
  (Section 7.5) even to solve the cross-plugin context-handoff problem —
  each domain's private memory stays isolated; only an explicit
  publish/read task-context blackboard crosses domain lines.

---

## 7. Planned Architecture: Dynamic Model-Tier Routing & Cross-Plugin
Orchestration

**Status: planned, not built.** Everything in this section is intended
architecture for future rounds, verified against the codebase as it
exists today (Section 3's capability list) — it is written here so future
work has a single source of truth to build toward, not because any of it
is live. Where this section says a component doesn't exist yet, that was
confirmed by direct code inspection, not assumed.

### 7.1 Why

Today, Codey-OS runs the coding agent against one fixed model per role —
Qwen2.5-Coder-7B for execution, Qwen2.5-1.5B for planning, nomic-embed for
embeddings (`utils/config.py`) — regardless of how simple or complex a
task is. The intent is for the coding capability (and, as more capability
domains are added — a research assistant, a personal-assistant/"secretary"
plugin — those domains too) to classify each incoming task's difficulty
and route it to an appropriately-sized model tier: smaller, faster models
for simple work, larger, more capable models for architecture, refactors,
multi-file changes, algorithms, concurrency, and security-sensitive work.
Beyond model selection, Codey-OS as an OS should be able to route — and,
where a request genuinely needs more than one kind of expertise, *split*
— a single request across multiple capability domains in the correct
order (e.g. "research X, then implement it": the research capability
runs first, and its findings actually reach the coding step as usable
input, not merely as a sequencing artifact). This should be reachable
identically from the CLI, TUI, GUI, and the background daemon.

### 7.2 What already exists vs. what's missing

- `capability_registry`/`tool_router` (Section 2) already select *which
  capability* handles a task, by lexical keyword-overlap plus a learned
  success-rate/speed/recency score. This is task-to-capability routing,
  not model-tier selection, and the two must stay conceptually separate
  (7.3).
- `agent_orchestrator`'s 5-agent deliberation loop (Section 2, Section 4)
  is fully implemented — Planner → Critic → Optimizer → Capability →
  Safety, weighted voting, Safety veto — but is not called anywhere at
  runtime today; only its own demo and test exercise it. Its agents are
  heuristic/structured-prompt logic, not separate model calls, so wiring
  it into real execution is inexpensive once there's something worth
  routing to (see the coding-agent-as-capability gap below).
- The coding agent itself (`core/agent.py`) is not a CCOS capability —
  it sits outside the plugin/capability system entirely, reached today
  through two independently-maintained call paths (`main.py`, used by
  the CLI and, via subprocess, the GUI; and `core/task_executor.py`, the
  daemon, which applies its own permission overrides). Only auxiliary
  helpers around it (git, static analysis, peer escalation, error
  recovery, task queue, finetune) are wrapped as capabilities today.
- No model-tier routing exists in any form yet. A second, smaller coder
  model path (`SECONDARY_MODEL_PATH`) is already configured but is
  currently only exercised by the fine-tuning/LoRA-swap path, not by any
  general-purpose tiering logic.
- No shared context/memory layer exists between capability domains.
  `ccos_memory` (Section 2) is OS-bookkeeping-only with no plugin
  consumers; the coding agent's five-tier memory (Section 3) is, by
  design, kept private to it. One compound skill
  (`ccos/plugins/compound/skill_camera_capture_tts`) already demonstrates
  that a single task *can* sequence capability calls across plugin
  categories — but the data computed at each step is currently discarded
  rather than passed to the next step, so the mechanism to actually hand
  context forward between steps doesn't yet work even where the
  sequencing itself does.

### 7.3 `ModelTierRouter` — a new, separate service

Model-tier selection is deliberately **not** an extension of
`tool_router`. `tool_router` decides *which capability* handles a
request, scored by keyword/performance history over discrete functions.
`ModelTierRouter` is a second-stage decision, made *after* a capability is
already selected, answering a different question: which size/class of
model, for which role (planner, coder, embedding), within that
capability's domain. Conflating the two would force capability-scoring
logic onto a model-sizing decision it isn't suited for.

- **Tier selection** is done by a lightweight, non-LLM classifier per
  domain (coding first) — keyword/length/pattern heuristics, not a model
  call — feeding a `(domain, role, tier) → model reference` config table.
  Which specific model family backs each tier (e.g. whether the planner
  tiers stay on the existing Qwen2.5 family or move to a different one) is
  an explicit open decision, deferred until the resource-aware loading
  infrastructure below exists and can be validated with real on-device
  data — this document intentionally does not hardcode that choice.
- **Generalization beyond coding**: every reference is keyed by
  `(domain, role, tier)`, never by a coding-specific model name, so a
  future research or secretary plugin gets tier routing by declaring its
  own roles/tiers in its plugin manifest (extending the existing
  `hardware_requirements` field's pattern with a parallel `model_tiers`
  declaration) and calling the same shared router — not by re-implementing
  classifier-and-loader logic per plugin.

### 7.4 Resource-aware loading — one authority, not two

Codey-OS has a documented history of crashes from concurrent model loads,
and today that risk is live in a concrete way: the daemon (`core/daemon.py`)
already calls the model loader directly at multiple points in its own
code, entirely independent of any tier-routing logic. Any new loading
system must not add a second independent decision-maker on top of that —
it must replace both with one.

- A single **resource gate** — not a hardcoded RAM threshold — decides,
  at load time, whether multiple model tiers/roles can stay resident
  simultaneously or whether one must be unloaded before another loads. It
  composes `device_manager`'s one-time hardware inventory with live
  signals from `core/sysmon.py`/`core/thermal.py`/`core/observability.py`
  (current RAM headroom, thermal state, active load), expressed as
  "current headroom minus a safety margin" rather than a fixed number —
  this is deliberate, since the same logic is expected to run on
  higher-RAM hardware later (a Linux desktop, a higher-RAM phone), not
  just today's device.
- This resource gate is the **sole authority** for load/unload/keep-resident
  decisions. The daemon's existing direct model-loader calls must become
  a client of this gate rather than a second, independent actor — this is
  the concrete fix for this project's known crash pattern, not a
  parallel safeguard alongside it.
- The model loader itself needs a slot concept (acquire/release/list
  current slots) to support this; it does not have one today.

**Amendment (2026-08-08, Ish): no fixed concurrency ceiling.** The
original framing above (built during 7.4's first scoping pass) treated
"never both the 7B and 1.5B resident at once" as effectively hard —
`core/loader_v2.py`/`core/planner_loader.py`'s own code and docstrings
currently encode it that way, and `planner_loader.py`'s docstring
explicitly calls it "Ish's decision, not negotiable here." That's
superseded as of this amendment:

- **There is no hardcoded cap on how many models may be resident.** The
  gate admits as many concurrently-resident models — across the daemon
  and any CLI process, per 9.2/9.3's multi-agent direction — as the live
  system budget and telemetry actually support at that moment. This
  replaces a fixed invariant with a computed one: the real limits are
  RAM/swap headroom (per 8's `NEW-21` correction — a per-load cost
  estimate compared against headroom, not headroom-minus-margin alone),
  thermal state, and whatever `telemetry_engine`/`observability` signals
  indicate about current system load — not a hardcoded "two models max"
  or "never both" rule.
- **The gate also owns CPU core/thread allocation for inference, not
  just admission.** As the number of concurrently-resident models
  changes, the gate is responsible for adjusting how many CPU
  threads/cores each running model's inference is allowed, so total
  compute demand stays inside what the device can sustain — this is a
  second axis the gate arbitrates, not a separate mechanism bolted on
  later.
- **One ceiling remains absolute and is not negotiable by the gate**:
  a single model must never be admitted if it alone exceeds what the
  system can handle, regardless of what else is or isn't resident. The
  removed constraint was the "only one at a time" rule between models
  that individually fit; "don't load something too big for this device
  at all" stays a hard admission check.
- **Future direction, not this round's scope**: Ish anticipates multiple
  small models running concurrently becoming the normal case (see 9.3's
  model-size-class declarations), and wants task-appropriate fallback —
  if a smaller/cheaper model can correctly handle a given task, prefer
  it over a larger resident one. That's a routing decision (closer to
  7.3's `ModelTierRouter`, and to task-capability matching, than to the
  gate's own admission logic) and is **not** part of 7.4's build — noted
  here so 7.4's gate is designed to not foreclose it (e.g. the gate
  should expose "would this smaller model fit right now" as an
  answerable question), not so it gets built now.
- This does not relax RAM discipline (CLAUDE.md rule 2) — it replaces a
  blunt binary rule with a computed one that's supposed to be *more*
  accurate about real headroom, not looser. Given `NEW-21`'s
  demonstrated case where a naive headroom check would have approved a
  load that then drove swap from 1.2GB to 5.6GB in ~10 seconds, the
  budget computation itself needs to stay conservative in practice even
  though the ceiling is no longer a fixed model count.

### 7.5 Cross-plugin request splitting and context handoff

Decomposing one user request into an ordered sequence of capability calls
across multiple domains (e.g. research → coding) is a new capability,
built on top of `agent_orchestrator` once it's wired to real execution —
it is not the same thing as that wiring itself. The orchestrator, once
connected, can correctly execute *one* capability call given a
deliberation result; request-splitting adds the outer loop that turns a
compound goal into an ordered, cross-domain sequence of such calls.

Context needs to move between steps in two ways:

- **In-flight**: `plugin_manager.call_capability` needs a context
  argument threaded through each step, replacing today's behavior where a
  step's computed output is silently discarded rather than handed to the
  next step.
- **Durable**: for handoffs where steps aren't adjacent in time (a
  research step that itself fans out before its findings are ready),
  something needs to hold that data until the next step reads it.

This durable piece is deliberately **not** a general shared-memory grant
across all plugins. Each capability domain keeps its own private memory
exactly as isolated as it is today (Section 3's five-tier memory stays
coding-only, and any future domain gets the same treatment) — collapsing
that isolation would create a single point of failure across every
plugin and undercut the reason that separation exists in the first
place. Instead, the durable handoff is a narrow, purpose-built
**task-context blackboard**: a store keyed by task/step ID, holding only
what a capability explicitly *publishes* for a later step to read — never
ambient access to another capability's private memory. This also gives
the daemon's task queue a natural, durable home for per-task state as it
moves through resource-aware scheduling.

### 7.6 Rollout order

Building this is dependency-ordered, not parallelizable end to end:
1. The resource gate and slot-aware loader (7.4), including migrating the
   daemon's existing direct loader calls onto it — this has to exist
   before any tier logic can safely act on a tier decision.
2. The task classifier and tier config for the coding domain only (7.3),
   reconciling rather than duplicating the coding plugin's existing
   separate planner-invocation paths.
3. Wrapping the coding agent as a real CCOS capability, migrating its
   existing call paths (CLI/GUI and daemon) onto that one boundary rather
   than adding a third path alongside them, with the capability wrapper
   owning its own permission surface explicitly instead of inheriting
   whatever the calling context happens to set.
4. The in-flight context-passing fix (7.5) and the task-context
   blackboard (7.5), designed together since one needs the other to be
   useful for non-adjacent handoffs.
5. Wiring `agent_orchestrator`'s deliberation to real execution — cheap,
   since its agents are heuristic rather than model-backed, but
   meaningfully changes behavior the first time it runs, since the Safety
   Agent's veto becomes live against real actions rather than a
   demonstration.
6. Multi-domain request splitting (7.5), which depends on all of the
   above being in place — it's the first point where capability-as-plugin,
   context-passing, and the durable blackboard all compose together.

---

## 8. Open Items Still Needing Resolution

**Resolved since first draft:**
- `core/recovery.py` — confirmed complete, working code (read in full).
  Decision: **keep, wire up** during unification. See Section 3.
- `core/observability.py` — confirmed complete, working code (read in
  full). Decision: **keep, wire up** during unification. See Section 3.
- `docs/architecture.md` — will be replaced by a new architecture doc
  reflecting Codey-OS's actual unified structure once unification is
  designed. No action needed now; noted so the eventual doc-cleanup pass
  doesn't treat this as a simple "keep or archive" case — it's a planned
  rewrite.

**Still open:**
- TTS is broken on both `core/voice.py` and `ccos/plugins/speech/tts_speech`
  (confirmed by Ish — neither currently works). Needs: get one working,
  verify it, remove the other. STT (voice input) has no CCOS equivalent at
  all, so `core/voice.py` (or a rewrite) is needed regardless of the TTS
  outcome.
- ~~Possible duplicate tracking between `core/recovery.py`'s built-in
  success-rate history and `core/strategy_tracker.py` — compare before
  wiring `recovery.py` up, to avoid two systems tracking the same
  thing.~~ **Resolved 2026-07-30:** already handled in Phase 2, see
  Section 3's Learning/preference-tracking row.
- ~~The small cleanup list (6 confirmed-safe-to-delete files from the repo
  audit) — paused per your instruction, revisit after this document is
  signed off.~~ **Resolved 2026-07-30:** 5 of the 6 (`test_optimize_me`
  x4 under `ccos/data/staging/`/`ccos/data/versions/`, `test_patch.txt`)
  were already deleted in commit `dd49c1d`. The 6th
  (`ccos/plugins/research/__init__.py`) is **not actually safe to
  delete** — the original audit flagged it as UNUSED because it's
  content-empty, but it's a standard Python package marker, structurally
  identical to the equally-empty `__init__.py` in every sibling plugin
  dir (`plugins/`, `speech/`, `system/`, `vision/`, `coding/`), all of
  which are required for the package to import. Correcting the record
  rather than deleting on the stale classification: keep it.
- Root-level and `docs/` UNCLEAR files from the repo audit —
  **itemized and mostly resolved 2026-07-30:**
  - `TODO.md` — **deleted.** Fully superseded: its unchecked lint-debt
    items already live in `NEW_ISSUES.md:1813-1823` and
    `WORK_QUEUE.md:208-209`; checked items are historical in
    `CHANGELOG.md`. `docs/TODO2.md` updated to note the deletion.
  - `Codey-OS-audit.md`, `MODEL_COMPARISON.md`, `PRIVACY.md`,
    `docs/importantdoc.md` — **keep, still active/current content**, but
    none are listed in `README.md`'s docs table (`Codey-OS-audit.md` is
    referenced elsewhere; the other three currently have no inbound link
    from README at all). Confirmed discoverability gap, logged as
    NEW-27 in `NEW_ISSUES.md`.
  - `QWEN.md` — kept (active, equivalent to `CLAUDE.md` for the Qwen CLI
    tool); its directory-tree section listed already-deleted
    `TODO.md`/`test_patch.txt`, now removed, but the tree is still
    materially incomplete (omits `CLAUDE.md`, `Codey-OS-audit.md`,
    `PENDING_ISH_DECISIONS.md`, `PROJECT_LOG.md`, `PROJECT_PLAN.md`,
    `QWEN.md` itself, `WORK_QUEUE.md`). Not fully fixed this round —
    logged as part of NEW-27. **Superseded 2026-08-08 (explicit
    instruction from Ish):** `QWEN.md` merged into `CLAUDE.md` and
    deleted — Qwen CLI sessions are no longer part of this project's
    active workflow, so a separate file (and its stale-tree problem) no
    longer applies. `CLAUDE.md` now carries an accurate, directory-level
    (not per-file) structure map instead, deliberately avoiding the
    per-file-inventory approach that caused this staleness in the first
    place.
  - `CHANGELOG.md` — **keep, active.** Linked from `README.md:177` and
    `docs/version-history.md`; most recently touched 2026-07-30. No
    action needed.
  - `AUDIT_REPORT.md` — **Resolved 2026-08-08 (Ish's explicit decision:
    archive).** Not a duplicate of `Codey-OS-audit.md` (that's a
    severity-rated bug audit; this was a June-13 "Codey-V3" era
    architecture/feature-inventory + investor-pitch document with no
    current equivalent, content stale, predates CCOS and the Codey-OS
    rename). Moved to `docs/archive/AUDIT_REPORT.md` with an archival
    header noting its historical-only status; not deleted.
  - `docs/TODO2.md` — **ambiguous, not resolved.** Old (2026-03-29,
    v2.7.2-era) deferred-items list; not linked from README, not fully
    re-verified against the current codebase. At least one item is
    already contradicted by the current code (see the note added to the
    file itself). Needs a scoped re-verification pass, not a keep/delete
    call made now. Logged as NEW-27 in `NEW_ISSUES.md`.

---

## 9. Amendment (2026-08-05, Ish): Multi-Agent Platform Direction

**Status: documented direction only.** This section records an explicit,
direct, in-session decision from Ish, dated 2026-08-05, per CLAUDE.md
rules 1 and 8's requirement that scope changes of this kind be logged,
not inferred. It is a deliberate amendment to this already-signed-off
document — see PROJECT_LOG.md's 2026-08-05 entry for the log record. As
of this amendment, **no code has changed** — the scheduler/resource-bus,
the plugin-manifest extensions, and any Aigentik-CLI integration
described below are all future work, tracked in `WORK_QUEUE.md`, not
built. Do not read this section as describing current running behavior.

### 9.1 The decision

Codey-OS is confirmed as a **multi-agent platform**: an OS shell (CCOS)
that runs multiple domain agents — the existing coding agent, and future
domain agents (e.g. a personal-assistant/communications agent, a research
agent) — side by side, each registered as a capability/plugin the shell
can discover, route to, monitor, and gate resource access for. This is a
scope expansion of Section 1's original framing, not a contradiction of
it: Section 1 already described the coding agent as "the first" capability
inside a shell "built to register, run, monitor, and eventually extend
capabilities beyond coding." This amendment makes explicit what was
previously only implied — that "beyond coding" means genuinely independent
domain agents, potentially with their own process, own model, and own
event loop, not just auxiliary tool-plugins around the coding agent (the
shape everything in Section 3 currently has).

### 9.2 Concurrency model — the resource-safety answer

Multiple domain agents will **not** all run local models concurrently by
default. A scheduling/resource-bus layer gates which models actually run,
based on live hardware state (RAM headroom, thermal/CPU headroom) and
event triggers — when resources aren't available, work **queues** rather
than running. This is a hard design constraint, not a nice-to-have.

This directly reinforces, and does not relax, CLAUDE.md rule 2's RAM
discipline. It is also not a new concept invented by this amendment —
Section 7.4's "resource gate" (a single authority for load/unload/keep-
resident decisions, composing `device_manager`'s hardware inventory with
live `sysmon`/`thermal`/`observability` signals) is exactly this
mechanism. What this amendment changes is scope: Section 7.4 was written
assuming one process (Codey-OS's own daemon) and one domain (coding).
Under the multi-agent direction, the same resource-gate concept must
eventually arbitrate across **multiple agent processes**, potentially
including agents that are not Codey-OS subprocesses at all (see 9.4's
Aigentik-CLI example, which runs its own independent `llama-server`).
That generalization is not designed yet — Section 7.4/7.6's existing
rollout order (resource gate first, coding-domain-only) is still the
correct starting point; the multi-agent case is documented here as the
direction that work must not be built in a way that forecloses.

### 9.3 Per-agent model-size-class declaration

Not every domain agent needs the 7B coding model. Ish is already running
a 4B model (Qwen3-4B via `llama.cpp`) as a working example, in a separate
project, Aigentik-CLI (see 9.4). Smaller models are the expected norm
for most domain/plugin agents, not an exception. Concretely, this means
the plugin/agent manifest shape must eventually declare a model-size
class or resource footprint per agent — extending Section 7.3's
`(domain, role, tier)` tiering concept and the existing
`hardware_requirements` manifest field's pattern (see
`ccos/core/capability_registry.py`'s `Capability.hardware_requirements`)
with a parallel declaration, rather than assuming one shared 7B model
across every agent. The concrete manifest schema for this is scoped in
the new blueprint document, `docs/agent-plugin-blueprint.md` — that
document also states plainly that today's real `manifest.json`/
`Capability`/`Plugin` schema does not yet have these fields; they are
proposed, not implemented.

### 9.4 Aigentik-CLI as the motivating example

Aigentik-CLI (`~/Aigentik-CLI`, a fully separate git repo, not part of
Codey-OS) is an existing, already-functional local AI communications
assistant: a standalone Node.js process (`index.js`) that watches Gmail
via IMAP IDLE and handles Google Voice SMS (forwarded as email), running
its own `llama-server` instance serving Qwen3-4B on `127.0.0.1:8080`,
with its own JSON-file data store (`data/*.json` — contacts, calendar,
rules, profile) and its own natural-language owner-command interface.
It is the concrete shape of "an existing agent with its own process, own
model, own event loop, own data store" that the multi-agent direction
needs to be able to integrate. Ish wants to understand what integrating
it into Codey-OS would concretely require — this amendment scopes that
question; it does not answer or implement it. See
`docs/agent-plugin-blueprint.md` for the worked-example writeup, and
`WORK_QUEUE.md` for the follow-up item to actually scope an integration
plan.

### 9.5 The Agent Registry substrate already exists, in seed form

`ccos/core/capability_registry.py`'s `CapabilityRegistry` (register/
query/find-by-task/performance-tracking over `Capability` records) and
`ccos/core/plugin_manager.py`'s `PluginManager` (disk discovery under
`ccos/plugins/<category>/<name>/manifest.json`, dynamic `importlib`
loading, capability registration from a manifest's `capabilities` list)
are the seed of what a multi-agent "Agent Registry"/"Plugin System" needs
— they are not being replaced by a new system. What they don't do today,
and would need extending for genuinely independent domain agents (as
opposed to today's in-process tool-plugins): register something that
isn't a Python module loaded via `importlib` into the same process (e.g.
Aigentik-CLI's separate Node.js process), and carry a model-size-class/
resource-footprint declaration (9.3) that a future resource gate (9.2)
can act on. Both are scoped as design work in `docs/agent-plugin-blueprint.md`,
not built here.

### 9.6 What this amendment does NOT change

The self-improvement gate (Section 5) is untouched. Ish authorized the
multi-agent platform **vision**, not activation of `goal_engine`,
`auto_improvement_loop`, `capability_optimizer`, or `skill_recombiner`.
Those remain gated off from live execution exactly as Section 5
describes, per CLAUDE.md rule 1 — nothing in this amendment constitutes
the explicit, direct, in-session activation instruction that rule
requires, and this amendment should not be read or cited as one.

### 9.7 Rollout order

This amendment does not replace Section 7.6's build order — it joins
onto it at a specific point, rather than running in parallel end to end:

1. **Build the resource gate for the coding domain only** (7.6 step 1,
   unchanged). This has to exist first regardless of the multi-agent
   direction — it's the direct fix for the daemon's live concurrent-load
   bug (7.4), and there is nothing to generalize until a single-domain
   gate is real.
2. **Design work that doesn't touch running code can proceed in
   parallel with step 1**: the manifest schema extension (9.3 —
   `agent_type`, `model_tiers`, `resource_footprint`, `event_triggers`,
   `permissions`, `data_store`) and the Aigentik-CLI integration scoping
   (9.4). Neither depends on the gate existing, since neither is being
   implemented against it yet — both are recorded in
   `docs/agent-plugin-blueprint.md` and `WORK_QUEUE.md` as design-only.
3. **Only after step 1 is real** does it make sense to generalize the
   resource gate to arbitrate across multiple agent processes (9.2),
   because that generalization is designed against the gate's actual
   API and behavior, not a hypothetical one. Implementing the manifest
   fields from step 2 against the gate, and any actual Aigentik-CLI
   integration work, both wait for this step — building either earlier
   would mean coding against an interface that doesn't exist yet.
4. Steps 2–6 of Section 7.6 (tier classifier, coding-as-capability,
   context passing, orchestrator wiring, request splitting) are
   unaffected by this amendment and keep their existing order; the
   multi-agent generalization (this section's step 3) can happen
   alongside them once step 1 is done, since neither depends on the
   other.

In short: **one resource gate, built once, for one domain, first —
design the multi-agent extensions in parallel on paper, but don't build
against the gate's multi-agent API until the gate itself exists.**

---

## 10. This Document's Role

Once you sign off, this is the spec every future Qwen prompt gets checked
against. If a restructuring step would contradict something here (e.g.
drop a capability from Section 3 without a logged reason, or activate
self-improvement without the Section 5 gate being met), that's a stop-and-
flag moment, not something to proceed through quietly.

Signed Off by Ish. Amended 2026-08-05 (Ish) — see Section 9. Amended
2026-08-09 (Ish) — see Section 11.

---

## 11. Amendment (2026-08-09, Ish): Model Orchestrator Architecture — models as ephemeral workers

**Status: documented direction, ties existing planned work (7.3, 7.4,
9.2, 9.3) into one coherent picture and adds new specifics (structured
handoff, a fuller resource profile, per-model requirement declarations).
Nothing here is built. `core/resource_gate.py` (Section 7.4, built and
code-reviewer-approved as of 2026-08-09) already implements the
admission-math slice of this — the RAM/swap/thermal-based "can this be
admitted right now" question — but does not yet implement the fuller
resource profile, structured handoff, or per-model declarations
described below. This section describes where that work is headed, not
what exists.**

### 11.1 The mental model: Codey is the manager, models are employees

Models are not permanently-resident intelligence — they're **ephemeral
workers**: loaded when a specific job needs them, performing that job,
passing a result onward, and getting unloaded when the orchestrator
decides the resources are better used elsewhere. Accessibility services,
shell, filesystem, vision, browser, and similar system-level facilities
are **tools**, not models — many steps in a task need no model at all.
The **Model Orchestrator** sits above all of this: it decides which
model (if any) needs to run, when, what information it receives, and
when it's done. This generalizes Section 7.3's `ModelTierRouter` concept
and Section 7.4's resource gate into one named architectural layer,
rather than introducing a third mechanism alongside them.

### 11.2 Structured handoff between stages, not context-dumping

When one stage's output feeds the next (e.g. a reasoning step decides
what to do, then a tool executes it, then a vision step interprets the
result), the orchestrator passes a small structured record between
stages — not the entire prior conversation. Illustrative shape (not a
finalized schema):

```json
{
  "task": "Find John's latest Gmail message",
  "current_app": "com.google.android.gm",
  "screen_state": {
    "description": "Gmail inbox",
    "relevant_elements": [{"text": "John Smith", "type": "email_row"}]
  },
  "next_action": "open_email",
  "confidence": 0.94
}
```

This is a concrete instance of Section 7.5's in-flight context-passing
fix and durable task-context blackboard — 7.5 already commits to
threading context between capability calls instead of discarding it;
this amendment specifies that the threaded content should be a compact
structured record scoped to what the next stage actually needs, not a
full conversation dump. Smaller handoffs mean less has to stay in
context (and, where relevant, less has to stay resident in RAM) between
stages.

### 11.3 Concurrency is an economic decision layered on top of admission, not a fixed rule

Section 7.4's 2026-08-08 amendment already removed the fixed
concurrency ceiling — the resource gate answers "**can** this be
admitted right now" from live budget, not a hardcoded model count. This
amendment adds a distinct layer on top: even when the gate *would*
admit a second model, the orchestrator may still choose to unload the
current model and load the next one sequentially, because a stage's
output was already reduced to a small structured handoff (11.2) that
doesn't need the prior model resident to be useful. **Admission
("can we") and scheduling ("should we, right now, for this task") are
two different questions** — 7.4's gate answers the first; the
orchestrator (not yet built) answers the second, using the gate's
answer as one input alongside sequencing/handoff efficiency. On today's
device this mostly means sequential load→work→unload→load-next; on
higher-RAM hardware the same orchestrator logic can choose to keep
several models resident, because the same computed-budget question
returns a different answer — same code, different hardware, different
execution strategy, which is the point of building this as a computed
decision rather than a hardcoded one.

### 11.4 A fuller resource profile than 7.4 currently computes

Section 7.4 (as built, sub-tasks 1-2) computes admission from RAM/swap
headroom, a per-load memory cost estimate, and CPU thread allocation.
This amendment names a fuller profile the orchestrator should eventually
draw on, extending 7.4 rather than replacing it:

- RAM available, RAM pressure (already in 7.4)
- CPU utilization, CPU temperature/thermal throttling state (already in
  7.4, via `core/thermal.py`)
- GPU utilization, NPU availability — **not yet in 7.4's scope**, no
  current code path measures either on this device
- Battery level, charging state — **not yet in 7.4's scope**
- Model load time, model memory requirement, context requirement,
  estimated inference cost — load time and inference cost are **not
  yet in 7.4's scope**; memory/context requirement are partially
  covered by `resource_gate.py`'s existing `ModelSpec`/`CostEstimate`

Building out GPU/NPU/battery/charging/load-time/inference-cost signals
is new, unscoped work — not a correction to 7.4, which was scoped and
built against what this device's coding-domain use case actually needs
today. Track as a future sub-task when a domain agent that actually
needs these signals (e.g. a vision or Android-control agent, see 11.6)
is scoped.

### 11.5 Per-model requirement declarations

Extending Section 9.3's proposed manifest fields (`model_tiers`,
`resource_footprint`) with the additional per-model attributes implied
above: a priority class (e.g. "vision," "tool/function routing"), an
estimated load time, and whether a given capability (e.g. vision) is
required versus optional for a given model. Illustrative, not a
finalized schema:

```
Qwen3-VL-4B      — RAM: ~3.5GB+, vision: required, CPU: moderate/high,
                    priority: vision, load time: medium
FunctionGemma-270M — RAM: low, vision: no, CPU: low,
                    priority: tool/function routing, load time: very low
```

This is additive to 9.3's proposed schema, not a separate one — same
status as 9.3 itself: proposed, not read by any code today.

### 11.6 Worked example (illustrative — describes a future domain agent, not current Codey-OS scope)

A request like "Open Gmail and find the latest email from John" would,
under this architecture, decompose as: (1) a reasoning stage (e.g.
Qwen3-4B) determines the steps, then unloads; (2) an Android-control
stage executes via the accessibility tree — no model required for this
step if the tree is sufficient; (3) only if the accessibility tree can't
adequately describe what's on screen does a vision stage load (e.g.
Qwen3-VL-4B), analyze a screenshot, return a structured result (11.2),
and unload; (4) the orchestrator reloads the reasoning stage only if
needed for a next step. **This describes a future Android-control/vision
domain agent that does not exist in Codey-OS today** — Codey-OS
currently has one domain agent (coding). This example illustrates the
target architecture's shape, per Section 9's multi-agent direction; it
is not a commitment to build Gmail/Android-automation capability in the
near term.

### 11.7 Decision logic should be deterministic-first, not "ask a model"

Much of the orchestrator's decision-making should be ordinary,
deterministic software — not a model call for every routing decision.
Illustrative:

```
if available_ram < required_ram: unload_idle_models()
if thermal_state == CRITICAL: reduce_concurrency()
if task.requires_vision: schedule(vision_model)
if accessibility_tree_sufficient: skip_vision()
if confidence < threshold: request_second_pass()
```

This matches Section 7.3's existing design intent for the task
classifier (explicitly a "non-LLM heuristic classifier," not a model
call) — this amendment generalizes that same deterministic-first
principle to the orchestrator's broader scheduling/handoff decisions,
not just task-tier classification.

### 11.8 What this does not change

This amendment does not modify `core/resource_gate.py`'s existing,
twice-reviewed, approved admission logic (Section 7.4) — it names the
layer above it (scheduling/orchestration) and the layer's future inputs
(11.4's fuller resource profile), without requiring any change to what's
already built. It does not commit to building vision or Android-control
capability now — Section 9's multi-agent direction already establishes
that future domain agents are in scope; this amendment describes what
their *scheduling* should look like once they exist, not a decision to
build them yet. It does not change Section 5's self-improvement gate.
