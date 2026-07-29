```
  ██████╗ ██████╗ ██████╗ ███████╗██╗   ██╗       ██████╗ ███████╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝      ██╔═══██╗██╔════╝
 ██║     ██║   ██║██║  ██║█████╗   ╚████╔╝ █████╗██║   ██║███████╗
 ██║     ██║   ██║██║  ██║██╔══╝    ╚██╔╝  ╚════╝██║   ██║╚════██║
  ╚██████╗╚██████╔╝██████╔╝███████╗   ██║        ╚██████╔╝███████║
   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝         ╚═════╝ ╚══════╝
```

**A local-first AI agent operating system for Termux/Android (and any Linux
system).** 100% local by default — no cloud dependency required, cloud
inference is an opt-in fallback.

Codey-OS starts from a fully-capable AI coding agent and wraps it inside an
OS-like shell, **CCOS** (Cognitive OS): a capability registry, plugin
manager, tool router, and a 5-agent internal deliberation system with a
safety veto, all running on top of a sandboxed execution environment. The
OS shell doesn't replace the coding agent — it governs and exposes it.
Coding is the first and most mature capability domain; the shell is built
to register, route to, and eventually extend well beyond it.

Formerly developed as separate Codey-v2/v3 and CCOS codebases — now
unified as **Codey-OS**, started and stopped as one system.

---

## Quick Start

```bash
git clone <this-repo> ~/Codey-OS
cd ~/Codey-OS
./install.sh
```

`install.sh` installs system dependencies, builds `llama.cpp`, downloads the
default local models, and prints backend-configuration instructions. See
[docs/installation.md](docs/installation.md) for the full manual walkthrough
and hardware requirements.

Once installed, bring the whole system up with one command:

```bash
codey-start   # daemon + GUI + TUI, all together
codey-stop    # clean shutdown of everything codey-start brought up
```

`codey-start` is the primary entry point. It starts the daemon (if not
already running), launches the GUI server in the background
(`http://localhost:8888` by default), and drops you into the interactive
TUI in the foreground — both stay live simultaneously and read from the
same dashboard data, so neither shows a different picture from the other.
The older fragmented entry points (`codeyOS`, `codeydOS`, `ccos_main.py`,
`gui/start.sh`) still exist underneath and are what `codey-start`
orchestrates — you generally don't need to call them directly anymore.

### Backend: local or remote

Two independent knobs control where inference runs — the coding agent and
the planner can even point at different backends:

```bash
export CODEY_BACKEND=local            # 7B coding agent — default
export CODEY_BACKEND_P=local          # 1.5B planner — defaults to CODEY_BACKEND if unset
```

Each accepts `local` | `openrouter` | `unlimitedclaude`. For example, to
keep the planner on-device while routing the agent to OpenRouter:

```bash
export OPENROUTER_API_KEY="sk-or-..."
export OPENROUTER_MODEL="anthropic/claude-sonnet-4-5"
export CODEY_BACKEND="openrouter"
export CODEY_BACKEND_P="local"
```

UnlimitedClaude works the same way via `UNLIMITEDCLAUDE_API_KEY`,
`UNLIMITEDCLAUDE_MODEL`, and `UNLIMITEDCLAUDE_PLANNER_MODEL`. The embedding
model (RAG retrieval, port 8082) always runs locally regardless of backend.
Run `./install.sh` (or re-run it) to see the full, current set of
copy-pasteable examples — it's kept in sync with `utils/config.py`.

---

## What Codey-OS can do

The coding agent's own core intelligence (tool-use loop, five-tier memory,
recursive draft→critique→refine self-refinement) is the primary capability
and is not yet wrapped as a discoverable CCOS capability in its own right —
it's what CCOS is built to eventually route to like everything else, but
today it's still the direct entry point. Everything below it **is** wrapped
and registered with CCOS's capability registry:

| Capability | What it does |
|---|---|
| RAG retrieval | Searches the local knowledge base, injects relevant chunks into context |
| Static analysis | Runs the best available linter on write; `/review` command |
| Git integration | Branch management, AI-generated commit messages, conflict detection |
| Voice (TTS/STT) | Text-to-speech output and speech-to-text input via Termux:API — **TTS is currently broken on both this and CCOS's own `tts_speech` plugin; being consolidated, not yet fixed** |
| Thermal/system monitoring | Live CPU/RAM/temperature/battery monitoring; throttles inference threads under thermal stress |
| Fine-tuning export | Exports interaction history and generates a Colab/Kaggle notebook to train a personal LoRA adapter |
| Task queue | Background task creation, status tracking, and cancellation |
| Daemon control | Read-only daemon status queries and task cancellation |
| Error recovery | Adaptive fallback when a tool fails (write→patch, import error→pip install, file-not-found→search, test failure→isolate and re-run), with history-adapting strategy selection |
| Peer CLI escalation | Delegates to Claude Code / Qwen CLI / Gemini CLI when stuck, with explicit consent before any file leaves the device |

Also already native to CCOS (no wrapping needed): `system_info`,
`camera_capture`, `tts_speech`, plus a few auto-generated compound skills
that chain two of the above together (e.g. capture a photo → speak the
result).

### Unified dashboard

The GUI (`http://localhost:8888`) and the TUI both render from the same
live data source — CPU/thermal state, RAM, daemon health, model status per
backend, and what capabilities are registered and active. They're started
together by `codey-start` and are guaranteed to never disagree about system
state.

---

## Architecture

Short version: a Unix-socket daemon (`codeydOS`) runs three purpose-built
models — a 7B coding agent, a 1.5B planner/summarizer, and an embedding
encoder for RAG — behind a CLI/TUI client (`codeyOS`) and the browser GUI.
CCOS sits above this as the OS shell: capability registry, plugin manager,
tool router, and the 5-agent deliberation/safety-veto layer, all in
`ccos/`.

Full detail (three-model design, memory/session persistence, context
compression) lives in [docs/architecture.md](docs/architecture.md) — note
that doc currently documents the coding agent's own model architecture and
hasn't yet been rewritten to describe the CCOS shell layer on top; that
rewrite is tracked separately, not part of this change.

---

## Self-improvement — present, gated off by default

`ccos/core/capability_optimizer.py`, `skill_recombiner.py`,
`goal_engine.py`, and `auto_improvement_loop.py` implement autonomous
self-improvement — detecting weak capabilities, generating improved
versions, testing them in the sandbox, and generating new compound skills
from observed usage patterns. This code exists and is tested, but it is
**not wired into the live execution path**. Activation is a deliberate,
signed-off decision gated on a period of stable, observed real-task
operation through the sandbox/safety-veto path — Codey-OS does not modify
or extend itself autonomously today.

Governance in brief: all generated code and plugin installs run sandboxed
first; the Safety Agent (highest weight in the 5-agent deliberation) can
veto any plan; old plugin versions are never deleted and every install can
be rolled back.

---

## Docs

| Doc | Covers |
|---|---|
| [docs/installation.md](docs/installation.md) | Requirements, one-line and manual install |
| [docs/commands.md](docs/commands.md) | CLI flags and the most-used in-session slash commands |
| [docs/configuration.md](docs/configuration.md) | Daemon config file, env vars |
| [docs/architecture.md](docs/architecture.md) | Three-model design, memory/session persistence |
| [docs/knowledge-base.md](docs/knowledge-base.md) | RAG retrieval / knowledge base setup |
| [docs/tools-embedding-pipeline.md](docs/tools-embedding-pipeline.md) | Dataset ingestion/embedding pipeline design |
| [docs/pipeline.md](docs/pipeline.md) | Training data pipeline (`pipeline/`) |
| [docs/fine-tuning.md](docs/fine-tuning.md) | Fine-tuning via Colab |
| [docs/fine-tuning-kaggle.md](docs/fine-tuning-kaggle.md) | Fine-tuning via Kaggle |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common issues |
| [docs/security.md](docs/security.md) | Threat model and mitigations |
| [docs/version-history.md](docs/version-history.md) / [CHANGELOG.md](CHANGELOG.md) | Release history |

`CODEY_OS_MASTER_VISION.md` in the repo root is the authoritative,
maintained spec for what Codey-OS is and where it's headed — the source
this README itself is checked against.

---

## Security

Codey-OS runs as a persistent daemon, executes shell commands, and loads
local LLMs — more capable, and more risk, than a simple chat tool. Read
[docs/security.md](docs/security.md) before running it on a device with
sensitive data.

---

## License

MIT — see [LICENSE](LICENSE).
