# QWEN.md — Read This First

## What this project is

Codey-OS is a local-first AI agent operating system for Termux/Android (and any Linux system). It unifies two previously-separate codebases — the **Codey-OS core coding agent** (`core/`, `tools/`, `utils/`, `main.py`) and the **Cognitive OS layer (CCOS)** (`ccos/`) — into a single system governed by one OS shell (`codey-start` / `codey-stop`). The OS shell discovers, routes, monitors, and eventually self-improves capabilities; the coding agent remains the primary capability, now wrapped and registered.

## Authoritative spec

`CODEY_OS_MASTER_VISION.md` in this repo root is the signed-off, canonical specification for what Codey-OS is and will be when finished. Before any structural change, wrapping, deletion, or architectural decision:
1. Re-read the relevant section of `CODEY_OS_MASTER_VISION.md`
2. If a task would conflict with it (e.g. drop a listed capability without a logged reason, activate self-improvement without its stated gate, let the GUI/TUI diverge, reintroduce fragmented entry points) — **STOP and flag it back to Ish** rather than proceeding.
Nothing in this repo should end up contradicting that document. If you believe it needs to change, that's a conversation to have explicitly, not a decision to make unilaterally mid-task.

## Current structure (as of 2026-07-27)

```
Codey-OS/
├── .github/                          # GitHub workflows
├── assets/                           # Static assets (0 .py files)
├── ccos/                             # CCOS: Cognitive OS layer (55 .py files)
│   ├── __init__.py
│   ├── core/                         # OS shell core modules (55 .py files)
│   │   ├── __init__.py
│   │   ├── agent_orchestrator.py     # 5-agent internal deliberation
│   │   ├── auto_improvement_loop.py  # Closed-loop improvement
│   │   ├── capability_optimizer.py   # Optimize weak capabilities
│   │   ├── capability_registry.py    # Central capability inventory
│   │   ├── device_manager.py         # Hardware inventory (CPU, RAM, GPU, cameras, mic)
│   │   ├── goal_engine.py            # Generate/prioritize improvement goals
│   │   ├── lifecycle_manager.py      # Top-level pipeline orchestrator
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   └── ccos_memory.py        # OS-level memory (SQLite + vector store)
│   │   ├── performance_tracker.py    # Per-capability metrics & versioning
│   │   ├── planner.py                # Execution planning with capability awareness
│   │   ├── plugin_manager.py         # Plugin discovery, loading, validation
│   │   ├── project_engine.py         # Long-horizon projects with milestones
│   │   ├── reflection_engine.py      # Post-task evaluation
│   │   ├── sandbox.py                # Isolated execution environment
│   │   ├── skill_recombiner.py       # Detect patterns → generate compound skills
│   │   ├── telemetry_engine.py       # Real-world execution monitoring
│   │   └── tool_router.py            # Best-tool selection for tasks
│   ├── data/                         # Persistent state (capabilities, goals, projects, memory DB)
│   ├── demo_*.py                     # Demo scripts for each CCOS subsystem
│   ├── plugins/                      # Plugin system (built-in + auto-generated)
│   │   ├── __init__.py
│   │   ├── compound/                 # Auto-generated compound skills
│   │   │   ├── skill_camera_capture_tts/
│   │   │   ├── skill_info_info/
│   │   │   └── skill_info_processes/
│   │   ├── research/
│   │   ├── speech/                   # TTS plugin (BROKEN — see open items)
│   │   │   └── tts_speech/
│   │   ├── system/                   # System info plugin
│   │   │   └── system_info/
│   │   └── vision/                   # Camera capture plugin
│   │       └── camera_capture/
│   └── tests/                        # CCOS test suite (7 test files)
├── codey3                            # Legacy entry point (to be retired)
├── codeyd3                           # Legacy entry point (to be retired)
├── core/                             # Codey-OS core coding agent (55 .py files)
│   ├── __init__.py
│   ├── agent.py                      # Main agent (75K) — three-model llama.cpp stack
│   ├── background.py                 # Background task handling
│   ├── checkpoint.py                 # Checkpoint/restore
│   ├── codeymd.py                    # Codey markdown handling
│   ├── context.py                    # Context management
│   ├── daemon.py                     # Persistent daemon (29K)
│   ├── daemon_config.py
│   ├── display.py
│   ├── embed_server.py               # Embedding server
│   ├── embeddings.py
│   ├── error_database.py
│   ├── filehistory.py
│   ├── filesystem.py
│   ├── finetune_prep.py
│   ├── fixmode.py
│   ├── githelper.py                  # Git integration
│   ├── inference.py
│   ├── inference_hybrid.py
│   ├── inference_openrouter.py       # Cloud fallback
│   ├── inference_v2.py
│   ├── learning.py                   # User correction/preference tracking
│   ├── linter.py                     # Static analysis / auto-lint
│   ├── loader_v2.py
│   ├── lora_import.py
│   ├── memory_v2.py                  # Five-tier memory system
│   ├── notes.py
│   ├── observability.py              # /status introspection (COMPLETE, DISCONNECTED)
│   ├── orchestrator.py
│   ├── peer_cli.py                   # Peer CLI escalation (Claude/Qwen/Gemini)
│   ├── peer_shell.py
│   ├── plannd.py
│   ├── planner.py
│   ├── planner_client.py
│   ├── planner_service.py
│   ├── planner_v2.py
│   ├── preferences.py
│   ├── project.py
│   ├── recovery.py                   # Error recovery / strategy switching (COMPLETE, DISCONNECTED)
│   ├── recursive.py                  # Recursive self-refinement
│   ├── retrieval.py                  # RAG retrieval
│   ├── search.py
│   ├── sessions.py
│   ├── skills.py
│   ├── state.py
│   ├── strategy_tracker.py           # Strategy success-rate tracking (overlaps recovery.py)
│   ├── summarizer.py
│   ├── symbolic_graph.py             # Mentalese symbolic graph
│   ├── sysmon.py                     # System monitoring
│   ├── task_executor.py
│   ├── taskqueue.py
│   ├── tdd.py
│   ├── thermal.py                    # Thermal-aware inference throttling
│   ├── tokens.py
│   └── voice.py                      # TTS/STT via Termux:API (BROKEN — see open items)
├── docs/                             # Documentation (0 .py files)
├── gui/                              # Browser-based GUI (1 .py file + HTML)
│   ├── index.html
│   └── server.py                     # WebSocket server
├── install.sh                        # Installation script
├── main.py                           # Codey-OS original entry point (62K)
├── pipeline/                         # Training data pipeline (25 .py files)
│   ├── __init__.py
│   ├── embedding/                    # Embedding backends (nomic, sentence-transformers)
│   ├── export/                       # Dataset export
│   ├── ingestion/                    # Data ingestion (HF, JSONL)
│   ├── normalization/                # Normalization, classification, quality
│   ├── run.py                        # Pipeline runner
│   ├── storage/                      # SQLite + vector storage
│   ├── synthetic.py                  # Synthetic data generation
│   └── transformation/               # Transformation rules, Termux-specific, validator
├── prompts/                          # Prompt templates (4 .py files)
│   ├── __init__.py
│   ├── critique_prompts.py
│   ├── layered_prompt.py
│   └── system_prompt.py
├── tests/                            # Codey-OS test suite (17 .py files)
│   ├── __init__.py
│   ├── security/                     # Security tests (path traversal, shell injection)
│   ├── test_agent_parsing.py
│   ├── test_breadth.py
│   ├── test_codeyignore.py
│   ├── test_finetune.py
│   ├── test_hallucination.py
│   ├── test_hybrid_inference.py
│   ├── test_json_parser.py
│   ├── test_learning.py
│   ├── test_memory.py
│   ├── test_orchestration.py
│   ├── test_parse_tool_call.py
│   ├── test_patch.py
│   └── test_self_modification.py
├── tools/                            # Agent tools (6 .py files)
│   ├── __init__.py
│   ├── file_tools.py
│   ├── kb_scraper.py
│   ├── kb_semantic.py                # Semantic knowledge base
│   ├── patch_tools.py
│   ├── setup_skills.sh
│   └── shell_tools.py
├── utils/                            # Utilities (4 .py files)
│   ├── __init__.py
│   ├── config.py
│   ├── file_utils.py
│   └── logger.py
├── AUDIT_REPORT.md                   # Repo audit findings
├── CHANGELOG.md
├── CODEY_OS_MASTER_VISION.md         # ← AUTHORITATIVE SPEC
├── LICENSE
├── MODEL_COMPARISON.md
├── NEW_ISSUES.md
├── PRIVACY.md
├── README.md
├── requirements.txt                  # Core + pipeline dependencies
├── setup.sh
├── setup_repo.sh
├── test_patch.txt
└── TODO.md

## Ground rules for working in this repo

1. **Read before you write.** Before modifying any file, read it first. Before adding a dependency, check `requirements.txt` and `install.sh`. Before changing architecture, re-read `CODEY_OS_MASTER_VISION.md`.
2. **Follow existing conventions.** Match the style, naming, imports, typing, and patterns already in the file or module you're editing. Don't introduce new patterns without a reason.
3. **Don't add features, abstractions, or error handling that wasn't asked for.** Three similar lines beat a premature abstraction. Only validate at system boundaries (user input, external APIs).
4. **Verify before claiming success.** Run the project's test suite, linter, and type checker before claiming a task is done. If you can't run them, say so explicitly.
5. **Keep `CODEY_OS_MASTER_VISION.md` as the source of truth.** If a task would contradict it, stop and flag it rather than proceeding.
6. **Keep `install.sh` current with anything we add.** Any time a task adds a new dependency (a pip package, a `pkg install` requirement, a new system binary) or changes a setup step, `install.sh` must be updated in the same task to reflect it — not left for later, and not installed ad hoc on the device without also being captured in the script. A fresh clone of this repo should be able to run `install.sh` once and end up with a fully working system, matching whatever the current state actually requires. If a task can't determine the right place to add something to `install.sh`, flag it rather than skipping the update silently.

**Summary counts (excluding .git, __pycache__):**
- 216 total files
- 169 Python files
- 55 in `core/` (Codey-OS agent)
- 55 in `ccos/core/` (CCOS OS shell)
- 25 in `pipeline/` (training data pipeline)
- 17 in `tests/` (Codey-OS tests)
- 7 in `ccos/tests/` (CCOS tests)
- 6 in `tools/`
- 4 in `utils/`
- 4 in `prompts/`
- 1 in `gui/`