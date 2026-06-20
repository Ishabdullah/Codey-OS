# Codey Cognitive OS (CCOS)

```
  ██████╗ ██████╗ ██████╗ ███████╗██╗   ██╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝
 ██║     ██║   ██║██║  ██║█████╗   ╚████╔╝
 ██║     ██║   ██║██║  ██║██╔══╝    ╚██╔╝
  ╚██████╗╚██████╔╝██████╔╝███████╗   ██║
   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝  ─ CCOS
  v3.0.0 · Adaptive Agent Operating System
```

> **CCOS is a modular, self-extending AI agent operating system built on Codey-V3.** It perceives its hardware, manages its own capabilities, generates improvement goals, executes long-horizon projects, deliberates through internal agents, and evolves based on real-world execution telemetry. 100% local. No cloud dependency required.

---

## 1. Project Overview

CCOS transforms Codey-V3 from a coding assistant into a **cognitive operating system** that:

- **Perceives** its hardware environment (CPU, RAM, GPU, cameras, microphones, network)
- **Manages** a registry of capabilities it can perform
- **Extends** itself by creating new plugins and compound skills from experience
- **Improves** continuously through reflection, optimization, and real-world telemetry
- **Deliberates** through an internal multi-agent committee before taking action
- **Executes** long-running projects that persist across sessions
- **Adapts** based on real execution behavior, not only simulated tests

CCOS is a **six-layer cognitive architecture** where each layer handles a distinct aspect of autonomous agent behavior.

---

## 2. Full System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 6: DIRECTION                            │
│                         Goal Engine                              │
│          Analyzes system state → generates priorities            │
├─────────────────────────────────────────────────────────────────┤
│                 LAYER 5: PERSISTENCE                             │
│                      Project Engine                              │
│       Goals → Projects → Milestones → Tasks → Resume            │
├─────────────────────────────────────────────────────────────────┤
│                  LAYER 4: ABSTRACTION                            │
│                    Skill Recombiner                              │
│       Detects patterns → generates compound skills               │
├─────────────────────────────────────────────────────────────────┤
│                  LAYER 3: LEARNING                               │
│  Reflection Engine · Performance Tracker · Telemetry Engine      │
│       Evaluate → measure → detect drift → feed back              │
├─────────────────────────────────────────────────────────────────┤
│                  LAYER 2: REASONING                              │
│          Planner · Agent Orchestrator (5 agents)                 │
│       Plan → critique → optimize → validate → approve            │
├─────────────────────────────────────────────────────────────────┤
│                  LAYER 1: EXECUTION                              │
│       Sandbox · Plugin Manager · Tool Router · Capabilities      │
│       Detect hardware → select tool → execute safely             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Modules

### Layer 1: Execution

| Module | Path | Purpose |
|--------|------|---------|
| **Device Manager** | `core/device_manager.py` | Hardware body awareness — detects OS, CPU, RAM, GPU, cameras, microphones, network, connected devices. The AI's "body model." |
| **Capability Registry** | `core/capability_registry.py` | Central inventory of all abilities. Each capability tracks name, description, implementation, dependencies, status, version, and performance metrics. |
| **Plugin Manager** | `core/plugin_manager.py` | Plugin lifecycle — discovery, dynamic loading, capability registration, execution, rollback. Plugins live in `plugins/<category>/<name>/`. |
| **Sandbox** | `core/sandbox.py` | Isolated execution environment. Enforces: no blocked commands, no path escapes, resource limits, timeouts. All generated code runs here. |
| **Tool Router** | `core/tool_router.py` | Selects the best tool for a task based on hardware availability, past performance, speed, and reliability. |

### Layer 2: Reasoning

| Module | Path | Purpose |
|--------|------|---------|
| **Planner** | `core/planner.py` | Decomposes user requests into execution plans. Checks capability registry, identifies gaps, sequences steps. |
| **Agent Orchestrator** | `core/agent_orchestrator.py` | Multi-agent internal deliberation system with 5 specialized agents: Planner, Critic, Optimizer, Capability, Safety. Weighted voting resolves disagreements. Safety agent can veto any plan. |

### Layer 3: Learning

| Module | Path | Purpose |
|--------|------|---------|
| **Reflection Engine** | `core/reflection_engine.py` | Post-task evaluation — checks correctness, tool selection quality, missing capabilities, improvement opportunities. |
| **Performance Tracker** | `core/performance_tracker.py` | Detailed per-capability metrics: success rate, execution time, retries, error frequency, version history, trend detection. |
| **Auto Improvement Loop** | `core/auto_improvement_loop.py` | Closed-loop system connecting reflection → tracking → optimization → registry update. Runs after every task. |
| **Capability Optimizer** | `core/capability_optimizer.py` | Detects weak capabilities, generates improved versions, tests in sandbox, compares old vs new, upgrades only if better. |
| **Telemetry Engine** | `core/telemetry_engine.py` | Real-world execution monitoring. Logs every real execution, detects performance drift, compares sandbox vs real results, computes system health score, feeds insights back into goal engine. |

### Layer 4: Abstraction

| Module | Path | Purpose |
|--------|------|---------|
| **Skill Recombiner** | `core/skill_recombiner.py` | Analyzes workflow history, detects repeated multi-capability patterns, generates new compound skills as plugins, validates in sandbox, registers if successful. |

### Layer 5: Direction

| Module | Path | Purpose |
|--------|------|---------|
| **Goal Engine** | `core/goal_engine.py` | Analyzes system usage, detects inefficiencies, generates candidate improvement goals, scores them by expected utility, prioritizes into a queue, injects top goals into the planner. |

### Layer 6: Persistence

| Module | Path | Purpose |
|--------|------|---------|
| **Project Engine** | `core/project_engine.py` | Converts high-value goals into persistent projects with milestones and tasks. Tracks progress across sessions. Auto-resumes unfinished work on startup. |
| **CCOS Memory** | `core/memory/ccos_memory.py` | Unified memory: SQLite structured DB (skills, workflows, configs, preferences, performance), event log, and vector store. |

### Lifecycle Manager

| Module | Path | Purpose |
|--------|------|---------|
| **Lifecycle Manager** | `core/lifecycle_manager.py` | Top-level orchestrator connecting the full pipeline: task → plan → execute → evaluate → improve → register → store. |

---

## 4. System Execution Flow

```
user request
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│  Device Manager          — detect hardware environment    │
│  Capability Registry     — query available abilities      │
│  Tool Router             — select best tool for task      │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│  Planner                 — generate execution plan        │
│  Agent Orchestrator      — 5-agent deliberation:          │
│    ├─ Planner Agent      — decompose goal                 │
│    ├─ Critic Agent       — find inefficiencies/risks      │
│    ├─ Optimizer Agent    — refine based on critique       │
│    ├─ Capability Agent   — verify tools/suggest alts      │
│    └─ Safety Agent       — validate + veto if unsafe      │
│  Weighted Voting         — resolve disagreements          │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│  Sandbox                  — execute in isolation          │
│  Plugin Manager           — call capabilities             │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│  Reflection Engine        — evaluate result               │
│  Performance Tracker      — log metrics                   │
│  Auto Improvement Loop    — optimize if needed            │
│  Telemetry Engine         — record real execution         │
│    ├─ Drift detection     — compare vs baseline           │
│    ├─ Gap analysis        — sandbox vs real results       │
│    └─ Health scoring      — system-wide assessment        │
└──────────────────────────────────────────────────────────┘
   │
   ▼
┌──────────────────────────────────────────────────────────┐
│  Skill Recombiner         — detect patterns, create skills│
│  Goal Engine              — generate improvement goals    │
│  Project Engine           — manage long-horizon projects  │
│  Memory System            — persist everything            │
└──────────────────────────────────────────────────────────┘
```

---

## 5. Intelligence Loops

CCOS operates through five interconnected feedback loops:

### Loop 1: Improvement Loop
```
task → reflection → performance tracking → capability optimizer → sandbox test → register
```
Optimizes existing capabilities. When a capability's performance drops below threshold, the optimizer generates an improved version, tests it in sandbox, and upgrades only if the new version outperforms the old.

### Loop 2: Recombination Loop
```
workflow history → pattern detection → skill generation → sandbox test → register compound skill
```
Creates new capabilities from combinations of existing ones. Detects repeated multi-step workflows and packages them as single-call compound skills.

### Loop 3: Goal Loop
```
usage data → goal generation → scoring → prioritization → planner injection
```
Generates system-level improvement priorities from observed data. Goals are scored by frequency, impact, complexity, dependency availability, and failure history. Top goals are injected into the planner for proactive execution.

### Loop 4: Project Loop
```
high-value goal → project creation → milestone decomposition → multi-session execution → resume
```
Converts top-scoring goals into persistent projects with milestones and tasks. Projects survive across sessions and auto-resume on startup.

### Loop 5: Telemetry Loop
```
real execution → logging → drift detection → gap analysis → health scoring → feedback
```
Captures real-world execution behavior, detects performance drift, compares sandbox vs real results, and feeds aggregated insights back into the goal and optimization loops.

---

## 6. Safety Model

CCOS enforces safety at multiple levels:

### Sandbox Enforcement
All generated code, plugin installations, and plugin tests execute inside the sandbox. Rules:
- No direct system file access outside allowed directories (`ccos/`, `/tmp`)
- No destructive commands (`rm -rf /`, `mkfs`, fork bombs)
- Resource limits (timeout, output size)
- No background persistence without approval

### Safety Agent Veto
The Safety Agent in the Agent Orchestrator has the highest voting weight (1.5) and can **veto any plan**. It checks:
- Blocked command patterns in goal text and step actions
- Destructive operations (delete, drop, format, truncate)
- System directory modifications
- Unsandboxed execution attempts

### Validation Pipeline
All generated code (improvements, compound skills, plugins) must:
1. Pass sandbox execution
2. Meet minimum success threshold (75%)
3. Be registered as `experimental` before becoming `active`
4. Have previous versions preserved (never deleted)

### Core Invariants
- No uncontrolled system modification
- No auto-deleting files
- No modifying core Codey V3 runtime directly
- All new abilities go through plugin system
- All plugins pass tests before activation
- Rollback available for every plugin install

---

## 7. Key System Properties

| Property | Status |
|----------|--------|
| Self-improving | Yes — capabilities optimize based on real performance data |
| Self-extending | Yes — creates new plugins and compound skills from experience |
| Multi-agent internal | Yes — 5 specialized agents deliberate before every action |
| Persistent memory | Yes — SQLite DB, event log, vector store, version history |
| Long-horizon execution | Yes — projects with milestones persist across sessions |
| Real-world adaptive | Yes — telemetry engine adapts based on actual execution behavior |
| Hardware-aware | Yes — device manager detects full hardware profile |
| Goal-directed | Yes — generates and prioritizes improvement goals autonomously |
| Sandboxed | Yes — all generated code runs in isolation |
| Backward compatible | Yes — all existing Codey V3 functionality preserved |

---

## 8. Plugin System

### Built-in Plugins

| Plugin | Category | Capabilities |
|--------|----------|-------------|
| `system_info` | system | `system.info`, `system.processes` |
| `camera_capture` | vision | `vision.camera_capture`, `vision.camera_list` |
| `tts_speech` | speech | `speech.tts`, `speech.tts_engines` |

### Auto-Generated Compound Skills

| Skill | Pipeline | Source |
|-------|----------|--------|
| `skill.info_processes` | `system.info` → `system.processes` | Workflow pattern detection |
| `skill.camera_capture_tts` | `vision.camera_capture` → `speech.tts` | Workflow pattern detection |

### Plugin Structure

Each plugin is a directory:
```
plugins/<category>/<name>/
├── manifest.json     — metadata, capabilities, dependencies
├── <module>.py       — implementation
└── test.py           — validation tests
```

---

## 9. Usage

### Run CCOS
```bash
cd /root/Codey-v3
python3 ccos_main.py
python3 ccos_main.py "read system information"
```

### Run Tests
```bash
cd /root/Codey-v3
PYTHONPATH=/root/Codey-v3 python3 ccos/tests/test_ccos.py              # Core (8 tests)
PYTHONPATH=/root/Codey-v3 python3 ccos/tests/test_improvement_loop.py   # Improvement (6 tests)
PYTHONPATH=/root/Codey-v3 python3 ccos/tests/test_skill_recombiner.py   # Skills (8 tests)
PYTHONPATH=/root/Codey-v3 python3 ccos/tests/test_goal_engine.py        # Goals (10 tests)
PYTHONPATH=/root/Codey-v3 python3 ccos/tests/test_agent_orchestrator.py # Agents (11 tests)
PYTHONPATH=/root/Codey-v3 python3 ccos/tests/test_project_engine.py     # Projects (13 tests)
PYTHONPATH=/root/Codey-v3 python3 ccos/tests/test_telemetry.py          # Telemetry (12 tests)
```

**Total: 66 tests across 7 test suites.**

### Run Demos
```bash
PYTHONPATH=/root/Codey-v3 python3 ccos/demo_improvement_loop.py     # Closed-loop improvement
PYTHONPATH=/root/Codey-v3 python3 ccos/demo_skill_recombiner.py     # Skill invention
PYTHONPATH=/root/Codey-v3 python3 ccos/demo_goal_engine.py          # Goal generation
PYTHONPATH=/root/Codey-v3 python3 ccos/demo_agent_orchestrator.py   # Multi-agent debate
PYTHONPATH=/root/Codey-v3 python3 ccos/demo_project_engine.py       # Long-horizon projects
PYTHONPATH=/root/Codey-v3 python3 ccos/demo_telemetry.py            # Real-world telemetry
```

### Execute a Task
Tasks flow through the full pipeline automatically:
```python
from ccos.core.lifecycle_manager import get_lifecycle_manager
result = get_lifecycle_manager().execute_task("capture a photo and speak the result")
```

### Projects Resume Automatically
On startup, the project engine loads all active projects and resumes the next pending task:
```python
from ccos.core.project_engine import get_project_engine
needs_attention = get_project_engine().resume_active_projects()
```

---

## 10. Data Persistence

| Data | Location | Purpose |
|------|----------|---------|
| Capabilities | `ccos/data/capabilities.json` | Registered capability definitions |
| Memory DB | `ccos/data/ccos_memory.db` | Skills, workflows, events, performance, telemetry |
| Goals Queue | `ccos/data/goals_queue.json` | Prioritized improvement goals |
| Projects | `ccos/data/projects.json` | Active/completed projects with milestones |
| Reflections | `ccos/data/reflections.jsonl` | Task reflection log |
| Plugin Versions | `ccos/data/versions/` | Backed-up plugin versions |

---

## 11. Design Philosophy

**Modular AI OS design.** Each cognitive function (perception, reasoning, learning, planning, execution) is a separate module with clear interfaces. Modules can be tested, replaced, or extended independently.

**Separation of concerns.** The six-layer architecture ensures each layer handles one aspect of agent behavior. Layers communicate through well-defined interfaces, not tight coupling.

**Sandbox-first execution.** All generated code, new plugins, and improvements run in isolation before touching the real system. Safety is enforced structurally, not by convention.

**Feedback-driven evolution.** CCOS does not assume it is correct. Every execution is measured, compared against baselines, and fed back into the improvement loops. The system evolves based on observed behavior.

**No hallucinated capabilities.** The AI does not assume abilities exist. It queries the capability registry before attempting any task. If a capability is missing, it generates a goal to create one.

**Version preservation.** Old versions of plugins are never deleted. Every improvement is backed up. Rollback is always available.

---

## 12. Directory Structure

```
Codey-v3/
├── ccos_main.py                          # CCOS entry point
├── ccos/
│   ├── __init__.py
│   ├── core/
│   │   ├── device_manager.py             # Hardware body awareness
│   │   ├── capability_registry.py        # Capability inventory
│   │   ├── plugin_manager.py             # Plugin lifecycle
│   │   ├── sandbox.py                    # Isolated execution
│   │   ├── tool_router.py                # Best-tool selection
│   │   ├── planner.py                    # Execution planning
│   │   ├── agent_orchestrator.py         # Multi-agent deliberation
│   │   ├── reflection_engine.py          # Post-task evaluation
│   │   ├── performance_tracker.py        # Metrics and versioning
│   │   ├── auto_improvement_loop.py      # Closed-loop improvement
│   │   ├── capability_optimizer.py       # Plugin optimization
│   │   ├── skill_recombiner.py           # Skill invention
│   │   ├── goal_engine.py                # Goal generation
│   │   ├── project_engine.py             # Long-horizon execution
│   │   ├── lifecycle_manager.py          # Full pipeline orchestrator
│   │   ├── telemetry_engine.py           # Real-world monitoring
│   │   └── memory/
│   │       └── ccos_memory.py            # Unified memory system
│   ├── plugins/
│   │   ├── system/system_info/           # System info plugin
│   │   ├── vision/camera_capture/        # Camera plugin
│   │   ├── speech/tts_speech/            # TTS plugin
│   │   └── compound/                     # Auto-generated skills
│   ├── tests/                            # 66 tests across 7 suites
│   ├── demos/                            # Interactive demos
│   └── data/                             # Persistent state
├── core/                                 # Original Codey V3 core (preserved)
├── tools/                                # Original Codey V3 tools (preserved)
└── main.py                               # Original Codey V3 entry point (preserved)
```

---

## License

MIT
