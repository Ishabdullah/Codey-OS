# Codey-OS — Project Ground Rules

## Start here (read this first, every new chat/context window)

1. **`CODEY_MASTER_PLAN.md`** — **the single authoritative plan.** It is
   the spec, the rules, the architecture, the current-state snapshot, and
   the ordered outstanding-work register, all in one file. Read its §0
   (how to read it), §2 (rules), §4 (where things stand), then §6/Appendix
   A for what's left. Don't contradict it without an explicit, logged
   decision from Ish.
2. **`PROJECT_LOG.md`** — reverse-chronological record of every round.
   Read the top few entries for what just happened.
3. **`NEW_ISSUES.md`** — the append-only findings ledger (`NEW-##` IDs).
   Authoritative for any individual finding's status.

**Superseded 2026-08-21:** `TODO.md`, `CODEY_OS_MASTER_VISION.md`,
`WORK_QUEUE.md`, `PROJECT_PLAN.md`, and `Codey-Restoricon-OS.md` were
merged into `CODEY_MASTER_PLAN.md` and moved to `docs/archive/`. They are
evidence only — the full reasoning and verbatim live-test output behind
each plan line. **Never plan work from them.**

## What this project is
Local-first AI agent OS for Android/Termux (Samsung S24 Ultra), being
built out into the operating system and single data backend for Ish's
construction/restoration business, **Restoricon, LLC** — target
**January 1, 2027, full scope** (Ish, 2026-08-21). Canonical spec:
`CODEY_MASTER_PLAN.md` — read it, don't contradict it without an
explicit, logged decision.

Codey-OS unifies two previously-separate codebases — the **Codey-OS core
coding agent** (`core/`, `tools/`, `utils/`, `main.py`) and the
**Cognitive OS layer (CCOS)** (`ccos/`) — into a single system governed
by one OS shell (`codey-start` / `codey-stop`). The OS shell discovers,
routes, monitors, and eventually self-improves capabilities; the coding
agent remains the primary capability, wrapped and registered as one.

**Confirmed direction (Ish, 2026-08-05):** the product scope is a
**multi-agent platform** — the coding agent is the first domain agent,
not the whole system. **Extended (Ish, 2026-08-21):** Codey-OS is also
the single backend all Restoricon business data lives in, with two
"limbs" (a comms/inbox process and an Android device-action app, each a
fork of an existing standalone product) and three client surfaces over
one API and one auth system. See `CODEY_MASTER_PLAN.md` §3 and
`docs/agent-plugin-blueprint.md`; documented direction, largely not yet
implemented (see `CODEY_MASTER_PLAN.md` §6 for the rollout order).

## Current repo structure

A directory-level map with purpose notes — deliberately not a per-file
inventory (that level of detail goes stale fast and has produced repeat
findings, `NEW-26`/`NEW-27`, when it did). For exact file lists, list the
directory directly rather than trusting a cached tree here.

```
Codey-OS/
├── .github/            GitHub workflows + repo description
├── assets/             Static assets (mascot image, demo GIF)
├── ccos/                Cognitive OS layer (the OS shell)
│   ├── core/            OS shell modules: capability_registry, plugin_manager,
│   │                    agent_orchestrator, device_manager, sandbox,
│   │                    tool_router, telemetry_engine, performance_tracker,
│   │                    lifecycle_manager, planner, reflection_engine,
│   │                    memory/ (ccos_memory), plus the gated
│   │                    self-improvement modules (goal_engine,
│   │                    auto_improvement_loop, capability_optimizer,
│   │                    skill_recombiner — see rule 1)
│   ├── data/            Persistent CCOS state (capabilities, goals, projects, memory DB)
│   ├── demo_*.py        Demo scripts for each CCOS subsystem
│   ├── plugins/          Plugin system: compound/, research/, speech/, system/, vision/
│   └── tests/            CCOS test suite
├── core/                 Codey-OS coding agent: agent.py (main loop), daemon.py,
│   │                    loader_v2.py (model loading), memory_v2.py (five-tier
│   │                    memory), orchestrator.py, plannd.py/planner*.py,
│   │                    recursive.py (self-refinement), symbolic_graph.py,
│   │                    inference*.py, checkpoint.py, thermal.py, sysmon.py,
│   │                    observability.py, recovery.py, githelper.py,
│   │                    peer_cli.py/peer_shell.py, voice.py (TTS/STT, broken),
│                        and other coding-agent internals
├── docs/                 Documentation (installation, commands, configuration,
│   │                    architecture, security, fine-tuning, pipeline,
│   │                    knowledge-base, troubleshooting, version-history,
│   │                    agent-plugin-blueprint, TODO2 [old, needs re-verification])
├── gui/                  Browser-based GUI: index.html + server.py (WebSocket server)
├── lib/                  Shared shell-script helpers (e.g. gui_launch.sh, sourced
│                        by both codey-start and codeyOS)
├── pipeline/             Training data pipeline: ingestion, normalization,
│                        transformation, embedding, storage, export, run.py
├── prompts/              Prompt templates: system_prompt.py, layered_prompt.py,
│                        critique_prompts.py
├── tests/                Codey-OS test suite, including tests/security/
├── tools/                Agent tools: file_tools, patch_tools, shell_tools,
│                        kb_scraper, kb_semantic, setup_skills.sh
├── utils/                config.py, file_utils.py, logger.py
├── codey-start / codey-stop   Unified entry points (current, not legacy)
├── codeyOS / codeydOS         CLI / daemon launcher scripts
├── install.sh            Installation script — must stay current (see
│                        Working conventions below)
├── main.py               Codey-OS CLI entry point
├── CODEY_MASTER_PLAN.md        ← AUTHORITATIVE PLAN + SPEC, read first
├── AGENTS.md                   Start-here pointer for non-Claude agents
├── PENDING_ISH_DECISIONS.md    Fully resolved; record of four
│                              capability-wrapping decisions
├── PROJECT_LOG.md              Reverse-chronological round record, rules 7/9
├── NEW_ISSUES.md               Findings ledger (Confirmed/Suspected), rule 8
├── LIVE_TEST_QUEUE.md           Model-load verification steps deferred for
│                              Ish to run himself (not run by Claude live)
├── docs/archive/               Superseded docs — evidence only, never plan
│                              from these: CODEY_OS_MASTER_VISION.md, TODO.md,
│                              WORK_QUEUE.md, PROJECT_PLAN.md,
│                              Codey-Restoricon-OS.md, AUDIT_REPORT.md
├── Codey-OS-audit.md / MODEL_COMPARISON.md / PRIVACY.md
└── README.md / CHANGELOG.md
```

## Non-negotiable rules

1. **Self-improvement mechanisms** (`goal_engine`, `auto_improvement_loop`,
   `capability_optimizer`, `skill_recombiner`) are permanently gated off
   from live execution. Never activate, wire up, or remove this gate
   without an explicit, direct instruction from Ish given in that exact
   session — not inferred, not implied by a task description.

2. **RAM discipline.** This device has ~10.8GB RAM and has crashed before
   from concurrent model loads. Before any live test that loads the local
   models (the Qwen3.5-4B default, the embedding model, or a retired
   4B during migration): run `free -h` and record it. Never run more
   than one live model-load cycle at a time — a cycle isn't done until the
   model is confirmed unloaded (`ps aux | grep llama-server` showing
   nothing but the grep itself). Batch multiple test messages into one
   interactive session rather than separate invocations.

3. **Never kill processes by bare name pattern** (`pkill -f <name>`).
   Always track and kill a specific PID your own code spawned. This
   project has been bitten by this exact bug before (a blanket
   `pkill -f llama-server` killed unrelated model servers).

4. **Any process-lifecycle change** (daemon start/stop, PID files, kill
   logic, locks, the GUI server's binding/auth) requires the
   code-reviewer subagent's explicit approval before commit, regardless
   of how small the change looks. This category has produced this
   project's worst bugs — including a well-intentioned, already-reviewed
   fix that introduced a new self-race (a daemon reading its own
   preemptively-written PID as evidence a duplicate was running).

5. **Verification means real, verbatim output** — actual `git diff`
   text, actual timings, actual `free -h` numbers — never a paraphrase
   or a "tests pass" summary. A claim isn't verified unless the literal
   output backing it exists.

6. **Correct the record when a claim doesn't hold up.** If a
   re-investigation shows an earlier finding was overclaimed, downgrade
   it explicitly in the docs rather than leaving the stronger claim
   standing. This has happened before and handling it honestly was the
   right call.

7. **Distinguish "code complete" from "live verified"** in
   `CODEY_MASTER_PLAN.md` (§4 and Appendix A) and `PROJECT_LOG.md`. Never
   mark something fully done on code-complete/mock-tested evidence alone.

8. **Anything found outside a task's scope** — even something small —
   gets logged to `NEW_ISSUES.md` (rated Confirmed or Suspected based on
   actual certainty) and is not silently fixed or silently dropped. If
   it's queue-level work, it also gets a line in `CODEY_MASTER_PLAN.md`
   Appendix A.

9. **Update `CODEY_MASTER_PLAN.md` (§4 current state + Appendix A) and
   `PROJECT_LOG.md`** after every completed round, with specifics — not
   "improved" or "done."

10. Before creating a new subagent, check the current contents of
    `.claude/agents/` for one that already fits the job. Only create a
    new one if none of the existing agents genuinely cover it —
    subagent sprawl makes the pipeline harder to reason about, not
    easier.

11. **Keep `install.sh` current with anything we add.** Any time a task
    adds a new dependency (a pip package, a `pkg install` requirement, a
    new system binary) or changes a setup step, `install.sh` must be
    updated in the same task to reflect it — not left for later, and not
    installed ad hoc on the device without also being captured in the
    script. A fresh clone of this repo should be able to run `install.sh`
    once and end up with a fully working system, matching whatever the
    current state actually requires. If a task can't determine the right
    place to add something to `install.sh`, flag it rather than skipping
    the update silently.


12. **Never assume — read the artifact, and read all of it.** No factual
    claim about an external artifact (a model, library, API, binary, or
    config file) may be stated from prior knowledge, from docs about a
    *similar* thing, or from family resemblance to a related name. Check
    the artifact itself. Two traps this project has already hit
    (2026-08-22, Qwen3.5-4B's architecture — see `CODEY_MASTER_PLAN.md`
    §2 rule 14 for the full case):
    - **A model-family name is not evidence.** Qwen3.5 is not Qwen3 with
      a bigger number; a shared prefix implies nothing about layers,
      attention mechanism, or KV layout.
    - **Don't grep for the keys you expect.** Dump the full key/field set
      first, then narrow. A filtered read that confirms your expectation
      looks like verification and isn't.
    Reading files, parsing headers, and inspecting binary strings is
    cheap and loads nothing (rule 2 governs what actually needs care), so
    there is no excuse for guessing.

## Working conventions (not numbered "non-negotiable" rules, but expected)

- **Read before you write.** Before modifying any file, read it first.
  Before adding a dependency, check `requirements.txt` and `install.sh`.
  Before changing architecture, re-read `CODEY_MASTER_PLAN.md` §3.
- **Follow existing conventions.** Match the style, naming, imports,
  typing, and patterns already in the file or module you're editing.
  Don't introduce new patterns without a reason.
- **Don't add features, abstractions, or error handling that wasn't asked
  for.** Three similar lines beat a premature abstraction. Only validate
  at system boundaries (user input, external APIs).
- **Verify before claiming success.** Run the project's test suite,
  linter, and type checker before claiming a task is done. If you can't
  run them, say so explicitly.

### Workflow: Hub-and-Spoke Coordinator Delegation

The main agent (Claude / Antigravity coordinator) strictly coordinates each task step-by-step with specialized subagents. **Every subagent reports back to the coordinator before the next agent is dispatched:**

```
User Request -> Coordinator
   │
   ├─► 1. Dispatch project-architect (scope & design spec) ──► Reports back to Coordinator
   │
   ├─► 2. Dispatch implementer (build & run unit tests)    ──► Reports back to Coordinator (diff + test output)
   │
   ├─► 3. Dispatch code-reviewer (mandatory audit)         ──► Reports back to Coordinator (APPROVED / CHANGES REQUESTED)
   │      (If CHANGES REQUESTED -> Coordinator routes back to implementer/architect)
   │
   ├─► 4. Dispatch live-verifier (if real on-device test)  ──► Reports back to Coordinator
   │
   └─► 5. Coordinator runs test suites, updates ledgers (CODEY_MASTER_PLAN.md §4 + App A, PROJECT_LOG.md, NEW_ISSUES.md), and commits.
```

- **1. Scoping & Architecture**: Coordinator invokes **`project-architect`** (or **`agent-tool-designer`** / **`prompt-engineer`** via architect recommendation) to inspect context and produce a technical specification. Reports back to Coordinator.
- **2. Implementation**: Coordinator hands the scoped specification to **`implementer`**. The implementer writes code, runs unit tests, and reports the exact diff and test output back to Coordinator.
- **3. Mandatory Adversarial Review**: Coordinator hands the diff directly to **`code-reviewer`** for adversarial audit before any commit — mandatory for anything touching process control, concurrency, daemon/kill logic, or security/RBAC. `code-reviewer` reports `APPROVED` or `CHANGES REQUESTED` back to Coordinator. If rejected, Coordinator routes back to implementer.
- **4. Live Verification**: If the task requires on-device live validation (model loading, RAM/swap tracking, live process lifecycle), Coordinator invokes **`live-verifier`** to run tests and capture verbatim output back to Coordinator.
- **5. Ledger Updates & Final Commit**: Coordinator runs full test suites, updates the authoritative tracking ledgers (`CODEY_MASTER_PLAN.md` §4 + Appendix A, `PROJECT_LOG.md`, `NEW_ISSUES.md`), and commits the changes.

This pipeline applies to every task, with no shortcuts for changes that look small or obvious — that assumption is exactly what's caused this project's worst bugs before.

## When to stop and escalate instead of proceeding

- code-reviewer rejects the same fix twice without converging
- live-verifier shows the original symptom isn't actually resolved, or
  shows a new regression
- The work would touch `CODEY_MASTER_PLAN.md`'s own architecture, or
  any of the gated self-improvement mechanisms (see rule 1)
- Repeated Termux/device-specific failures suggesting an environment
  problem, not a code problem
- Anything genuinely ambiguous about product direction, not
  implementation detail
