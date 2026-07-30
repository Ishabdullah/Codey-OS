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
| **Learning / preference tracking** | Tracks user corrections and preferences, error-pattern learning over time | `core/learning.py`, `core/strategy_tracker.py`, `core/error_database.py` | Already active (imported by `agent.py`). **Note:** `strategy_tracker.py` may overlap with `recovery.py`'s own built-in success-rate tracking (`record_error`/`get_success_rate`) — worth a direct comparison when wiring `recovery.py` up, to avoid tracking the same thing twice in two places. |
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
- Possible duplicate tracking between `core/recovery.py`'s built-in
  success-rate history and `core/strategy_tracker.py` — compare before
  wiring `recovery.py` up, to avoid two systems tracking the same thing.
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
    logged as part of NEW-27.
  - `CHANGELOG.md` — **keep, active.** Linked from `README.md:177` and
    `docs/version-history.md`; most recently touched 2026-07-30. No
    action needed.
  - `AUDIT_REPORT.md` — **not deleted, disposition still open.** Read in
    full: it is not a duplicate of `Codey-OS-audit.md` (that's a
    severity-rated bug audit; this is a June-13 "Codey-V3" era
    architecture/feature-inventory + investor-pitch document with no
    current equivalent). Content is stale (predates CCOS, predates the
    Codey-OS rename, doesn't reflect current architecture) but not a
    clean duplicate, so per CLAUDE.md rule 8 it wasn't deleted
    unilaterally. Needs Ish's call: archive or delete. Logged as NEW-27
    in `NEW_ISSUES.md`.
  - `docs/TODO2.md` — **ambiguous, not resolved.** Old (2026-03-29,
    v2.7.2-era) deferred-items list; not linked from README, not fully
    re-verified against the current codebase. At least one item is
    already contradicted by the current code (see the note added to the
    file itself). Needs a scoped re-verification pass, not a keep/delete
    call made now. Logged as NEW-27 in `NEW_ISSUES.md`.

---

## 9. This Document's Role

Once you sign off, this is the spec every future Qwen prompt gets checked
against. If a restructuring step would contradict something here (e.g.
drop a capability from Section 3 without a logged reason, or activate
self-improvement without the Section 5 gate being met), that's a stop-and-
flag moment, not something to proceed through quietly.

Signed Off by Ish.
