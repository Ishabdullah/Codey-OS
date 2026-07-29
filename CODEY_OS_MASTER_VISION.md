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
| **Coding agent (core intelligence)** | Reads/writes/edits files, executes tool calls, reasons over a codebase | `core/agent.py`, three-model llama.cpp stack (7B agent / 0.5B planner / embedding encoder) | Needs wrapping as the primary capability |
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

This replaces the current fragmented entry points (`codey3`, `codeyd3`,
`ccos_main.py`, `gui/start.sh`) as the primary way to run the system. Those
underlying pieces don't disappear — `codey-start` orchestrates them — but
the user-facing surface becomes these two commands. This also resolves the
earlier open question about the duplicate no-extension `codey3`/`codeyd3`
files found in the repo audit: those get retired in favor of this unified
pair rather than resolved as standalone duplicates.

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

---

## 7. Open Items Still Needing Resolution

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
- The small cleanup list (6 confirmed-safe-to-delete files from the repo
  audit) — paused per your instruction, revisit after this document is
  signed off.
- Root-level and `docs/` UNCLEAR files from the repo audit — same, paused.

---

## 8. This Document's Role

Once you sign off, this is the spec every future Qwen prompt gets checked
against. If a restructuring step would contradict something here (e.g.
drop a capability from Section 3 without a logged reason, or activate
self-improvement without the Section 5 gate being met), that's a stop-and-
flag moment, not something to proceed through quietly.

Signed Off by Ish.
