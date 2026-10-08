# Codey-OS

**A persistent, local-first AI agent platform for Android/Termux, combining a coding assistant with a business backend and a growing capability system.**

Codey-OS aims to become an extensible AI operating system and personal companion: an assistant that remembers context, uses tools, develops new capabilities, and improves through measured experience. Today, its most concrete components are a local coding agent, a background task daemon, the CCOS plugin layer, and **Restoricon Core**, a SQLite-backed construction and restoration business platform.

“Operating system” describes the agent and service layer running inside Termux; Codey-OS does not replace Android. The main development device is a Samsung S24 Ultra with approximately 10.8 GB of physical RAM. Other Linux environments have installer and CI support, but the complete service stack is Termux-oriented and has not been demonstrated as portable to every Linux distribution.

**Implementation audit: October 8, 2026.** This README reflects source execution paths, focused tests, and explicitly identified historical live evidence. A module's presence does not mean it runs in the normal application. Autonomous self-improvement, universal sandbox enforcement, and an evolving companion personality remain incomplete.

## What works today

- **Interactive coding:** load and search files, edit or patch code, execute shell commands, retain sessions, inspect changes, and run review, repair, or test-driven workflows. Planning and draft/critique/refinement paths exist within the coding engine.
- **Local inference:** one Qwen3.5-4B generation model serves coding and planning through `llama-server`; a separate local embedding model supports knowledge retrieval. Remote inference adapters are optional.
- **Persistent context:** project instructions in `CODEY.md`, saved sessions, notes, coding-style preferences, and retrieval hooks feed later interactions. This is useful persistence, not demonstrated general learning.
- **Background operation:** a Unix-socket daemon manages queued tasks, while shell launchers coordinate the daemon, Core API, and configured external services.
- **Business workflows:** Restoricon Core implements CRM, scheduling, operations, estimates, contracts, document/PDF workflows, financial records, and role-specific web surfaces over a shared database.
- **Capability extension:** CCOS discovers plugins and dispatches registered capabilities, including the coding agent itself, CRM reads, system tools, retrieval, and device integrations.
- **Measurement:** local telemetry, optional trajectory capture, a frozen coding benchmark, and candidate-promotion machinery provide infrastructure for evaluating changes.

## Capability maturity

**Verified** means successful tests or recorded execution evidence for the stated scope. It does not imply that every branch, device integration, or complete user journey has been exercised.

| Capability | Current classification | Evidence and boundary |
|---|---|---|
| Local model loading and coding entry path | Implemented and verified in recorded live runs | CLI and daemon route through the coding capability; prior device runs exercise local inference. No model was loaded during this README audit. |
| Resource admission and action gateway policy | Implemented and verified by focused tests | Admission logic and gateway behavior are tested; gateway coverage across actions is still partial. |
| Restoricon authentication and HTTP API | Implemented and verified by focused tests | Tests exercise authentication, temporary databases, and loopback HTTP. This is not a browser or production deployment certification. |
| CRM tool and sales copilot | Implemented and verified within limited live scenarios | October 6 logs record model-to-HTTP CRM queries against a database copy and copilot success/access denial. Broader task quality remains unmeasured. |
| Estimator and pricing persistence | Implemented and verified within tested scope | Calculation, storage, conversion, and API tests exist; historical database-copy runs cover selected workflows. Automated retailer pricing is incomplete. |
| Sessions, notes, preferences, project context | Implemented but unverified end to end in this audit | Active context injection exists. Automatic preference synchronization into `CODEY.md` is currently refused by the action gateway. |
| Knowledge retrieval and symbolic graph | Partially implemented / unverified quality | Retrieval and graph hooks exist; corpus coverage and end-to-end retrieval quality were not established. Symbolic inference is off by default. |
| Cloud models, voice, hardware actions, external limbs | Implemented but unverified end to end in this audit | Require provider credentials, Termux:API permissions, or separately installed applications. |
| Trajectory store, benchmark, promotion gate | Implemented and verified by focused tests | Measurement infrastructure exists; it does not establish autonomous capability gains. Trajectory recording is off by default. |
| Self-improvement, LoRA deployment, CCOS deliberation | Experimental, disabled, or incompletely integrated | Research mechanisms exist; the complete continuous improvement and safety-veto chain is absent from normal execution. |
| Evolving personal companion and autonomous domain workforce | Planned / partial foundations | Static identity, memory, and tool interfaces exist; relationship development and independently learning domain agents are not demonstrated. |

## Architecture

```text
codey / codey-start / codey-stop
  └─ lib/service_manager.sh
       ├─ codeydOS → core/daemon.py → queued task executor
       ├─ Restoricon Core HTTP API → services → SQLite + document storage
       └─ configured external services: Aigentik, tunnel, backups

codeyOS / main.py                         daemon queued tasks
  └─ CCOS PluginManager                       │
       └─ coding.run_agent capability ◄────────┘
            └─ core/agent.py
                 ├─ file / shell / notes / CRM / peer tool dispatch
                 ├─ context, sessions, preferences, retrieval
                 ├─ coding planner and recursive refinement
                 └─ inference routing
                      ├─ local llama-server: generation
                      └─ optional remote provider adapters

retrieval → local embedding server
CRM tool → authenticated Restoricon Core API
runtime hooks → local telemetry / optional trajectory store
```

The interactive CLI runs the coding engine in its own process; it is not simply a thin frontend to daemon-hosted inference. Background tasks use the same registered coding capability with subtask mode enabled. Model-server lifecycle and resource admission are separate concerns handled by the loader and resource gate.

The live coding planner/refinement mechanisms in `core/` are distinct from CCOS's proposed five-agent deliberation chain. CCOS contains orchestration, lifecycle, sandbox, safety-veto, reflection, optimization, and skill-recombination modules, but those modules do **not** collectively govern every normal CLI or daemon action.

| Location | Responsibility |
|---|---|
| [`main.py`](main.py), [`codeyOS`](codeyOS) | Interactive CLI, slash commands, direct task invocation |
| [`core/`](core/) | Coding agent, daemon, inference, memory, resource management, checkpoints, peer integrations |
| [`ccos/core/`](ccos/core/), [`ccos/plugins/`](ccos/plugins/) | Registry, plugin dispatch, capability wrappers, experimental OS mechanisms |
| [`restoricon_core/`](restoricon_core/) | Business database, authentication, services, HTTP API, web surfaces |
| [`tools/`](tools/), [`prompts/`](prompts/) | Coding tools, retrieval helpers, prompt construction |
| [`telemetry/`](telemetry/), [`codey-metrics`](codey-metrics) | Local runtime measurement and inspection |
| [`bench/`](bench/), [`pipeline/`](pipeline/) | Frozen evaluation harness and dataset preparation/export |
| [`tests/`](tests/), [`ccos/tests/`](ccos/tests/) | Regression, unit, integration, and security tests |

## Models, inference, and coding agents

The configured local generation default is **`Qwen3.5-4B-Q4_K_M.gguf`**. Coding and planning share the primary server, normally on port **8080**; local planning uses the model's thinking path rather than loading a separate planner. The retired Qwen2.5 7B/1.5B split is not the current local architecture.

**`nomic-embed-text-v1.5.Q4_K_M.gguf`**, normally on port **8082**, is a separate encoder for retrieval. Selecting remote generation does not make the embedding path remote. Local generation defaults to CPU operation (`n_gpu_layers=0`), with a configured interactive context of 65,536 tokens and a lower background-task ceiling. These are configuration values, not throughput, memory-safety, or answer-quality guarantees.

[`utils/config.py`](utils/config.py) defines `CODEY_BACKEND` for generation and `CODEY_BACKEND_P` for planning. Supported adapter values are `local`, `openrouter`, and `unlimitedclaude`; the planner defaults to the generation backend. Provider keys, model names, and base URLs are configurable. Remote adapters exist in the code, but provider availability and successful requests were not checked during this audit.

The agent's model-facing tool registry includes file reads/writes/patches/appends, directory listing, search, shell execution, note storage/removal, `crm_query`, and `peer_delegate`. Additional capabilities and slash commands are exposed through separate paths; the model does not automatically receive every CCOS plugin as a tool.

Peer CLI integration supports external coding assistants through `core/peer_cli.py` and `core/peer_shell.py`. Peer executables and the lazily imported `pexpect` package are separate prerequisites; the main installer does not currently ensure all of them. Its current behavior is deliberately uneven: model-driven peer delegation, the natural-language delegation path, and the CCOS peer wrapper are gated as high-impact actions without a confirmation channel and therefore refuse dispatch. Other paths, including `/peer` and parked escalation, still have gateway gaps. Do not interpret installed peer support as universally consent-mediated delegation.

## Memory, learning, and companion foundations

The working coding path uses loaded files, conversation/session persistence, project `CODEY.md`, notes, and persisted preferences when assembling context. Coding-style preferences are extracted with fixed patterns and stored in SQLite. The current gate prevents their automatic write-back into `CODEY.md`; this does not remove the separate preference store.

`core/memory_v2.py` implements multiple memory abstractions. Their names should not be mistaken for a complete cognitive architecture: project memory includes path/hash metadata, long-term memory is separate from the active knowledge-base store, and retrieval quality depends on populated data and a functioning embedding setup. Symbolic graph retrieval/prompt hooks exist, while the symbolic inference path requires `CODEY_SYMBOLIC=1` and is disabled by default.

Error history and retry hints can inform subsequent attempts, and recursive refinement can ask the model to critique and revise a draft. The separate `error_recovery` plugin exists, but its recovery machinery is not integrated into the live agent tool-failure path. Neither establishes persistent weight learning or reliable generalized self-correction. Identity and small-talk behavior provide companion foundations; an evolving personality, relationship model, sleep/consolidation cycle, and autonomous curiosity loop are not demonstrated features.

### Evaluation and self-improvement research

- `CODEY_TRAJECTORY=1` enables bounded trajectory recording; it is off by default. The store supports external outcome labels, evaluation/training separation, and filtered export.
- [`bench/`](bench/) contains eight frozen seed coding tasks, hidden graders, null/oracle controls, an append-only results ledger, and paired candidate-versus-baseline comparison. Harness errors are distinguished from agent failures.
- The promotion gate checks comparative evidence and regression criteria. The small seed suite is insufficient to claim broad intelligence or reliable general improvement.
- `CODEY_SELF_IMPROVE` accepts `off` (default), `shadow`, or `on`. These switches govern experimental CCOS mechanisms; setting them does not create a fully wired daemon self-improvement loop.
- Fine-tuning export/notebook generation and a LoRA adoption registry with rollback exist. Normal `--import-lora` refuses adoption because its evaluator is not implemented. `--lora-force-adopt` is an explicit, recorded operator override, not a benchmark pass.

No successful autonomous capability-improvement cycle or validated adapter deployment is claimed here. The direction is to establish trustworthy measurement, grounded verification, and reversible promotion before expanding autonomous learning.

## Restoricon Core and external integrations

Restoricon Core is the project's first substantial business domain. Its HTTP server wires authentication, auditing, CRM, communications, scheduling, automation, operations, finance, business operations, search/analytics, estimates, commissions, and territories into one service layer.

Implemented workflows include customer/property/project records, leads and tasks, scheduling, estimates with calculation/versioning/acceptance/share links and project conversion, contract PDFs and signatures, document handling, and financial records. The finance layer should not be read as a complete accounting system or payment processor. Vendored catalog/retailer-import components and pricing-job records do not establish an operating automated pricing worker.

The default API binds to **`127.0.0.1:8770`** and uses **`~/.codeyOS/restoricon.db`** unless configured otherwise. Web surfaces include `/quote`, `/admin`, `/portal`, `/sales`, `/pm`, `/tech`, `/subcontractor`, and `/estimates`. Their business data is served through authenticated, role-scoped API routes; login and intentionally public workflows have separate access rules.

The `crm_query` coding tool reaches Core through an authenticated CCOS client. Sales copilot endpoints provide scoped assistance over business data. Recorded live evidence is limited: October 6 testing used a database copy and a manually started inference server for the copilot; subsequent loader testing addressed that startup problem. These results do not prove complete browser workflows or production readiness.

**Codey-Aigentik** provides the external communications/inbox limb; the private Android agent is a separate device-action limb. Their applications are not bundled into this repository. The service manager expects a separately installed Aigentik checkout, while Core contains integration clients and bridge code. A device bridge without a real registered handler reports that it is disconnected rather than simulating success.

Termux:API plugins expose phone and sensor capabilities, and voice input/output uses Termux STT/TTS commands. They require the Android-side application, permissions, and working device services. Hardware, voice, external messaging, and the complete Android bridge were not exercised in this audit.

## Security and autonomy boundaries

Codey can execute commands and modify files with the permissions of its host user. Existing controls include workspace-aware filesystem access, `.codeyignore`, write/shell confirmations, checkpoints for permitted self-modification, daemon shell restrictions, and physical-memory admission checks that do not count zram as physical RAM.

The action gateway classifies mediated operations as `READ`, `ACT`, or `HIGH_IMPACT` and attempts to record their outcomes. High-impact actions without a confirmation channel are refused. **Coverage is incomplete:** plugin permission metadata is not a universal enforcement layer, the sandbox is not wrapped around every execution path, and outbound requests, database changes, git operations, and some peer paths still need consistent mediation. `confirm_available` describes a channel's availability; it does not itself obtain consent, and `ACT` is not universally fail-closed.

`--yolo` disables ordinary coding-agent write/shell confirmations. It does not bypass every high-impact gateway refusal. `--allow-self-mod` is a separate explicit scope with checkpoint enforcement. Neither option should be presented as enabling a safe autonomous self-development loop.

Restoricon uses bearer-token authentication, PBKDF2 password hashing, service-level role checks, and customer scoping. Its local bind is the default. Tunnels, cloud providers, messaging, and remote backups are separate configured network integrations, not implied by “local-first.”

**Local telemetry is enabled by default** and can be disabled with `CODEY_TELEMETRY=0`. Runtime hooks record operational measurements; `codey-metrics` inspects them. The old “No Telemetry” wording still found in some source/UI text is not accurate. Optional full-fidelity trajectories can contain task content; enable and export them deliberately.

## Installation and setup

The primary supported environment is **Android with Termux**, Python, a C/C++ build toolchain, and enough storage and physical memory for local models. Termux:API is needed for phone/voice functionality. External communications, tunnels, and backups require their own applications or credentials.

```bash
git clone https://github.com/Ishabdullah/Codey-OS.git ~/Codey-OS
cd ~/Codey-OS
bash install.sh
```

[`install.sh`](install.sh) detects supported package managers, installs Python dependencies, builds `llama.cpp`, downloads the generation and embedding GGUFs, prepares configuration, and installs launcher links. The source build targets commit `4f5406761517648c23dbd60ea5ade37f77a316c9`; an existing binary can be reused instead, so inspect any version-drift warnings. The installer can continue after some failures: check its final dependency/model checks rather than treating completion alone as success.

Dependencies are specified in [`requirements.txt`](requirements.txt) and the installer. Core libraries include Rich, NumPy, Requests, Watchdog, NetworkX, multipart parsing, and ReportLab; vector search can use `hnswlib` with a NumPy fallback. Dataset-pipeline dependencies are separate from ordinary inference needs. On Termux, compiled pandas/PyArrow dependencies are obtained through `pkg`, as described in the requirements comments. Inference uses the **`llama-server` binary**, not a required `llama-cpp-python` installation.

This audit checked installer syntax and CLI help; it did **not** repeat a fresh installation or download models. Some older installation guides contain superseded model/configuration details.

### Start with the coding CLI

```bash
python3 main.py --help
python3 main.py --version
python3 main.py --chat
python3 main.py "Explain this project's entry points"
python3 main.py --read main.py --chat
```

`codeyOS` is the installed launcher for the CLI. Direct `main.py` invocation is also supported and exposes the actual parser's options. A generation request can load a model; check available memory before starting local inference.

### Optional service stack

Review the active configuration and provision the separate services before using the full launcher:

```bash
codey config
codey status
codey start       # configured services in the background
codey-start       # services, then interactive TUI
codey logs
codey-stop
```

`codey` also supports `stop`, `restart`, and `help`; with no subcommand it starts services and opens the TUI. `codeydOS` is the lower-level daemon manager. The shared service manager coordinates Core, the daemon, Aigentik, and configured Cloudflare/Litestream/document-backup processes; these are not all self-contained components of a fresh clone.

For API development, the real entry point and options are:

```bash
python3 -m restoricon_core.api.server --help
# Use an isolated development database, never the live business store:
RESTORICON_DOC_STORE_PATH=/tmp/codey-readme-dev-docs \
  python3 -m restoricon_core.api.server --host 127.0.0.1 --port 8771 --db /tmp/codey-readme-dev.db
```

Starting the server does not provision every business role or external integration. Authentication setup lives in [`restoricon_core/auth.py`](restoricon_core/auth.py); there is no universal public default login advertised here.

## Configuration

Environment settings are defined in [`utils/config.py`](utils/config.py); [`config.json.example`](config.json.example) is the tracked service-configuration template used to create local configuration.

| Setting | Purpose |
|---|---|
| `CODEY_DIR` | Repository location; defaults to `~/Codey-OS` |
| `CODEY_MODEL`, `CODEY_EMBED_MODEL` | Generation and embedding GGUF paths |
| `CODEY_LLAMA_SERVER` | Override `llama-server` executable selection |
| `CODEY_N_CTX` | Generation context configuration; `--ctx` also provides a CLI override |
| `CODEY_BACKEND`, `CODEY_BACKEND_P` | Generation and planning backend selection |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_PLANNER_MODEL` | OpenRouter credentials and model choices |
| `UNLIMITEDCLAUDE_API_KEY`, `UNLIMITEDCLAUDE_MODEL`, `UNLIMITEDCLAUDE_PLANNER_MODEL` | UnlimitedClaude credentials and model choices |
| `CODEY_CONFIG_PATH` | Override the service configuration file lookup |
| `RESTORICON_DB_PATH`, `RESTORICON_API_HOST`, `RESTORICON_API_PORT` | Core database and standalone API defaults |
| `RESTORICON_DOC_STORE_PATH` | Core document-store location |
| `CODEY_TELEMETRY` | Local telemetry; `0` disables it |
| `CODEY_TRAJECTORY`, `CODEY_SYMBOLIC`, `CODEY_SELF_IMPROVE` | Optional recording and experimental cognition controls described above |

Service configuration lookup prefers `CODEY_CONFIG_PATH`, then `~/.codeyOS/config.json`, then `CODEY_DIR/config.json`. The daemon separately reads `~/.codeyOS/config.json`; do not assume the override consistently relocates every component's configuration. Secrets and external-service setup also have dedicated paths; inspect the configuration helper and service manager before deployment.

For remote inference, set the matching provider credentials and a model identifier available to your account, then select that adapter. For example, `CODEY_BACKEND=openrouter` with `CODEY_BACKEND_P=local` keeps the planner local. This is routing configuration, not a claim that any particular provider/model offering is currently available.

## Usage and development

Selected supported CLI workflows:

```bash
python3 main.py --plan "Plan a small refactor of this project"
python3 main.py --no-resume --chat
python3 main.py --fix path/to/script.py
python3 main.py --tdd path/to/source.py --tests path/to/test_source.py
python3 main.py --finetune --ft-model 4b --ft-days 30
```

The paths above are placeholders for files in your working project. Repair and test-driven commands can execute code and edit files. Fine-tuning exports data and notebook material; it does not train a local model by itself.

Inside an interactive session, `/help` lists commands. Useful groups include:

| Purpose | Commands |
|---|---|
| Load and inspect context | `/read <file>`, `/load <file-or-directory>`, `/context`, `/search <pattern>` |
| Review edits | `/diff [file]`, `/undo [file]`, `/review <file.py>` |
| Project and sessions | `/init`, `/memory`, `/sessions`, `/summarize`, `/cwd [path]` |
| Inspect memory/retrieval | `/learning`, `/rag <prompt>`, `/graph` |
| System integration | `/voice`, `/peer`, `/git` |
| Finish | `/exit` |

Some slash-command help text is older than the parser and gateway behavior. In particular, do not assume every peer path is enabled or that `--yolo` skips every confirmation mechanism. Use `python3 main.py --help` for accepted command-line flags.

### Tests and evidence

Tests cover the coding core, plugins, resource management, memory, security, telemetry, benchmark infrastructure, and Restoricon services/API. The CI workflow uses Ubuntu with Python 3.12, installs `requirements.txt`, and invokes pytest. CI configuration is not evidence of the latest run being green.

A focused, non-model test selection used for this audit is:

```bash
PYTHONDONTWRITEBYTECODE=1 CODEY_TELEMETRY=0 python3 -m pytest -q -p no:cacheprovider \
  tests/test_action_gateway.py tests/test_resource_gate.py \
  tests/test_trajectory.py tests/test_export_hygiene.py \
  tests/test_promotion_gate.py tests/test_pricing_repo.py \
  tests/test_restoricon_core/test_auth.py tests/test_restoricon_core/test_api.py
```

**Audit results: 553 targeted tests passed across two runs.** The selection above produced `488 passed in 66.73s`. A second run of `tests/test_bench_harness.py`, `tests/test_restoricon_core/test_b9_8_estimate_convert.py`, and `tests/test_b8_11_sales_copilot.py` produced `65 passed in 33.67s`. These cover policy/storage logic, the benchmark harness, estimate conversion, mocked copilot completions, and isolated API tests including loopback HTTP with temporary databases; they do not load a live inference model. CLI help and shell syntax checks also succeeded. Full-suite success, fresh installation, browser interactions, external providers, Android hardware, and production deployment were not established by this audit.

[`pytest.ini`](pytest.ini) excludes the benchmark's hidden task fixtures from ordinary collection: the benchmark harness runs those in isolated task copies. See [`bench/README.md`](bench/README.md) for evaluator mechanics. Before broad test runs, inspect fixtures and state paths: some integration paths can reach local services or inference. Tests involving business data must use copies or temporary stores.

Contributors should read [`AGENTS.md`](AGENTS.md), the rules in [`CODEY_MASTER_PLAN.md`](CODEY_MASTER_PLAN.md), and [`CLAUDE.md`](CLAUDE.md). Follow the repository's architect → implementer → reviewer → live-verifier workflow. For live model tests, record `free -h`, run only one model-load cycle at a time, and stop only the specific processes the test spawned. Process-lifecycle changes require explicit adversarial review.

## Known limitations and direction

The current platform is useful but still under active integration. Remaining work includes completing action mediation and permission enforcement; validating installation and real device workflows; expanding benchmark coverage; measuring retrieval and coding quality; connecting reflection and memory to trustworthy feedback; and demonstrating safe candidate promotion and rollback in actual use.

The broader vision remains a persistent personal companion and multi-domain AI operating system: coding as one capability among many, coordinated business and device agents, richer long-term memory, and the ability to build and improve capabilities over time. A unified multi-domain scheduler and backend-independent brain manager, reliable domain-agent autonomy, evolving companion behavior, and demonstrated continual improvement belong to that roadmap, not to a completed-feature list. NPU acceleration is also research direction rather than the default inference backend.

### Maintained documentation

| Document | Use |
|---|---|
| [`CODEY_OS_MASTER_BLUEPRINT.md`](CODEY_OS_MASTER_BLUEPRINT.md) | October 6 architecture census and ordered work packages; later source changes supersede parts of that snapshot |
| [`CODEY_MASTER_PLAN.md`](CODEY_MASTER_PLAN.md) | Project vision, mandatory rules, architectural decisions, and historical plan |
| [`PROJECT_LOG.md`](PROJECT_LOG.md), [`NEW_ISSUES.md`](NEW_ISSUES.md) | Recent changes, recorded live evidence, limitations, and per-finding status |
| [`AGI_AUDIT_PLAN.md`](AGI_AUDIT_PLAN.md), [`bench/README.md`](bench/README.md) | Improvement research direction and evaluation design |
| [`docs/agent-plugin-blueprint.md`](docs/agent-plugin-blueprint.md) | Domain-agent and plugin integration direction |
| [`docs/telemetry_layer_design.md`](docs/telemetry_layer_design.md) | Local measurement schema and design |
| [`ccos/plugins/device/termux_api/README.md`](ccos/plugins/device/termux_api/README.md) | Termux device capability details |
| [`docs/knowledge-base.md`](docs/knowledge-base.md), [`docs/pipeline.md`](docs/pipeline.md) | Knowledge-base and dataset workflows; check commands against current source |

Older installation, architecture, security, and command guides remain useful background but contain superseded statements. Archived plans under `docs/archive/` preserve evidence; they are not the active work queue. For exact runtime behavior, trace the current implementation and consult the latest issue/log entries.

## License

MIT — see [LICENSE](LICENSE).
