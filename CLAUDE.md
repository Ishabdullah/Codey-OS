# Codey-OS — Project Ground Rules

## Start here (read in this order, every new chat/context window)

1. **`TODO.md`** — the single ordered checklist of everything left to do,
   in dependency order. Check this first for current outstanding work and
   where it sits in sequence, before starting anything new.
2. **`CODEY_OS_MASTER_VISION.md`** — the canonical spec for what Codey-OS
   is and will be when finished. Don't contradict it without an explicit,
   logged decision.
3. **`WORK_QUEUE.md`** — the same ordered sequence as `TODO.md`, but with
   full evidence/history behind each item (why it's scoped the way it is,
   what's already been tried, live-verification detail). `TODO.md` is
   what to check off; `WORK_QUEUE.md` is what to read when you need the
   reasoning behind a `TODO.md` line.

## What this project is
Local-first AI agent OS for Android/Termux (Samsung S24 Ultra). Canonical
spec: `CODEY_OS_MASTER_VISION.md` — read it, don't contradict it without
an explicit, logged decision.

Codey-OS unifies two previously-separate codebases — the **Codey-OS core
coding agent** (`core/`, `tools/`, `utils/`, `main.py`) and the
**Cognitive OS layer (CCOS)** (`ccos/`) — into a single system governed
by one OS shell (`codey-start` / `codey-stop`). The OS shell discovers,
routes, monitors, and eventually self-improves capabilities; the coding
agent remains the primary capability, wrapped and registered as one.

**Confirmed direction (Ish, 2026-08-05):** the product scope is a
**multi-agent platform** — the coding agent is the first domain agent,
not the whole system. See `CODEY_OS_MASTER_VISION.md` Section 9 and
`docs/agent-plugin-blueprint.md`; this is documented direction, not yet
implemented (see `TODO.md`'s Phase 3 for the rollout order).

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
├── CODEY_OS_MASTER_VISION.md   ← AUTHORITATIVE SPEC
├── TODO.md                     ← ordered outstanding-work checklist, read first
├── WORK_QUEUE.md               Same order as TODO.md, with full evidence/history
├── PROJECT_PLAN.md / PROJECT_LOG.md   Phase tracking / reverse-chronological log
├── NEW_ISSUES.md               Findings log (Confirmed/Suspected), rule 8
├── LIVE_TEST_QUEUE.md           Model-load verification steps deferred for
│                              Ish to run himself (not run by Claude live)
├── Codey-OS-audit.md / MODEL_COMPARISON.md / PRIVACY.md
│   (docs/archive/AUDIT_REPORT.md — archived, June-2026 pre-CCOS era)
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
   7B/1.5B/embedding models: run `free -h` and record it. Never run more
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
   `PROJECT_PLAN.md` and `PROJECT_LOG.md`. Never mark something fully
   done on code-complete/mock-tested evidence alone.

8. **Anything found outside a task's scope** — even something small —
   gets logged to `NEW_ISSUES.md` (rated Confirmed or Suspected based on
   actual certainty) and is not silently fixed or silently dropped.

9. **Update `PROJECT_PLAN.md` and `PROJECT_LOG.md`** after every
   completed round, with specifics — not "improved" or "done."

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

## Working conventions (not numbered "non-negotiable" rules, but expected)

- **Read before you write.** Before modifying any file, read it first.
  Before adding a dependency, check `requirements.txt` and `install.sh`.
  Before changing architecture, re-read `CODEY_OS_MASTER_VISION.md`.
- **Follow existing conventions.** Match the style, naming, imports,
  typing, and patterns already in the file or module you're editing.
  Don't introduce new patterns without a reason.
- **Don't add features, abstractions, or error handling that wasn't asked
  for.** Three similar lines beat a premature abstraction. Only validate
  at system boundaries (user input, external APIs).
- **Verify before claiming success.** Run the project's test suite,
  linter, and type checker before claiming a task is done. If you can't
  run them, say so explicitly.

## Workflow

project-architect is the entry point for any new piece of work: read
context first, then decide which specialist(s) the task actually needs
before delegating.

- **CCOS capability/plugin work** (wrapping a function as a capability,
  writing or auditing a plugin manifest.json, deciding whether something
  is safe to expose to agent-driven planning, deciding which of
  Codey-OS's internal agents — Planner, Critic, Optimizer, Capability,
  Safety — should call a given capability): project-architect delegates
  design/scoping to **agent-tool-designer** first, then hands the scoped
  task to implementer.
- **Qwen prompt work** (system_prompt.py, layered_prompt.py,
  critique_prompts.py, plannd.py's PLANNER_PROMPT — tuning or debugging
  how the local 7B agent or 1.5B planner follows instructions):
  project-architect delegates to **prompt-engineer** first, then hands
  the scoped task to implementer if a separate implementation pass is
  needed.
- **General coding work** that doesn't fit either specialty above goes
  straight to **implementer**.
- **Every task**, regardless of which specialist scoped or built it,
  goes through **code-reviewer** before commit — mandatory for anything
  touching process control, daemon/kill logic, or security; a lighter
  pass otherwise. Loop back to whichever agent built it on rejection.
- **live-verifier** confirms on-device when a change needs real
  confirmation, not just unit/mock tests — after code-reviewer approves,
  before the round is considered done.
- **code-hygiene-auditor** runs as a periodic or explicitly requested
  read-only pass, separate from the per-task chain above. It never edits
  code. Its findings go to project-architect and get scoped into normal
  tasks through this same pipeline, exactly like any other finding.
- project-architect updates the tracking docs once a round is fully
  done, and adds a short explanatory note to any code touched for the
  first time in that round (see project-architect's own instructions).

This pipeline applies to every issue, with no shortcuts for changes that
look small or obvious — that assumption is exactly what's caused this
project's worst bugs before.

## When to stop and escalate instead of proceeding

- code-reviewer rejects the same fix twice without converging
- live-verifier shows the original symptom isn't actually resolved, or
  shows a new regression
- The work would touch `CODEY_OS_MASTER_VISION.md`'s own architecture, or
  any of the gated self-improvement mechanisms (see rule 1)
- Repeated Termux/device-specific failures suggesting an environment
  problem, not a code problem
- Anything genuinely ambiguous about product direction, not
  implementation detail
