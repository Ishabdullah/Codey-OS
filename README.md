# CODEY-V3

```
  ██████╗ ██████╗ ██████╗ ███████╗██╗   ██╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝╚██╗ ██╔╝
 ██║     ██║   ██║██║  ██║█████╗   ╚████╔╝
 ██║     ██║   ██║██║  ██║██╔══╝    ╚██╔╝
  ╚██████╗╚██████╔╝██████╔╝███████╗   ██║
   ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝   ╚═╝  ─ V3
  v3.0.0 · Persistent On-Device AI Agent with Symbolic Reasoning
```

> **Codey-V3 is a persistent, on-device AI coding agent with a symbolic reasoning layer.** It runs entirely in Termux on Android, maintains state across sessions, and reasons through a language-agnostic concept graph before generating code. 100% local. No telemetry. No cloud required.

[![Stars](https://img.shields.io/github/stars/Ishabdullah/Codey-V3?style=flat-square&color=gold)](https://github.com/Ishabdullah/Codey-V3/stargazers)
[![License](https://img.shields.io/github/license/Ishabdullah/Codey-V3?style=flat-square)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/Ishabdullah/Codey-V3?style=flat-square)](https://github.com/Ishabdullah/Codey-V3/commits/main)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?style=flat-square&logo=python)](https://python.org)

---

## What's New in v3.0.0

### Symbolic Reasoning Layer (Mentalese Engine)

Codey-V3 now reasons through a **symbolic concept graph** before generating code. Instead of predicting tokens from surface text, the agent:

1. Converts natural language into structured graph operations (OBSERVE, CAUSE, POSSESS, AGENTIVE, SPATIAL, TEMPORAL, INTEND)
2. Executes those operations against a persistent SQLite-backed NetworkX graph
3. Checks the graph for logical consistency (causal cycles, dangling references)
4. Renders the graph state back to natural language for the coder

The **coder never sees the original prompt** — only the symbolic graph state. This forces reasoning through structure.

### Multilingual Concept Memory

Embeddings now use `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384-dim, 50+ languages). The same concept described in English, Arabic, or Spanish maps to the same vector. Concepts in the graph store utterances in all known languages.

### Two-Step Training Pipeline

Fine-tuning data now includes `thought_trace` — each training example has:
- `observation`: raw user input
- `symbolic_graph`: the graph state (NetworkX adjacency list)
- `utterances`: parallel descriptions in multiple languages

The Colab notebook trains a two-step objective: given observation, predict symbolic_graph; given symbolic_graph, predict utterances.

---

## Architecture

```
                        ┌─────────────────────────────────────┐
                        │           User Input                │
                        │     "create fibonacci in python"    │
                        └──────────────┬──────────────────────┘
                                       │
                        ┌──────────────▼──────────────────────┐
                        │    Symbolic Pipeline (v3.0.0)       │
                        │                                     │
                        │  ┌─────────────┐                    │
                        │  │   Planner   │  1.5B model        │
                        │  │  (NL → ops) │  port 8081         │
                        │  └──────┬──────┘                    │
                        │         │ OBSERVE, CAUSE, INTEND    │
                        │  ┌──────▼──────┐                    │
                        │  │   Graph     │  NetworkX + SQLite │
                        │  │   Engine    │  language-agnostic  │
                        │  └──────┬──────┘                    │
                        │         │ graph state               │
                        │  ┌──────▼──────┐                    │
                        │  │ Deliberation│  consistency check  │
                        │  └──────┬──────┘                    │
                        │         │ enriched prompt           │
                        └─────────┼───────────────────────────┘
                                  │
                        ┌─────────▼───────────────────────────┐
                        │         Agent Loop                   │
                        │                                      │
                        │  ┌─────────────┐                    │
                        │  │    Coder    │  7B model          │
                        │  │  (graph →   │  port 8080         │
                        │  │  tool call) │                    │
                        │  └──────┬──────┘                    │
                        │         │ <tool>{...}</tool>         │
                        │  ┌──────▼──────┐                    │
                        │  │   Tools     │  write_file,       │
                        │  │  (execute)  │  shell, patch, ... │
                        │  └─────────────┘                    │
                        └──────────────────────────────────────┘

Memory Tiers:
  1. Working Memory    — currently loaded files (LRU eviction)
  2. Project Memory    — CODEY.md, config (never evicted)
  3. Long-term Memory  — multilingual embeddings (SQLite)
  4. Episodic Memory   — action log with observations
  5. Symbolic Memory   — concept graph (language-agnostic UUIDs)
```

---

## Quick Start

### On-Device (Termux)

```bash
# 1. Clone and enter the repo
git clone https://github.com/Ishabdullah/Codey-V3.git && cd Codey-V3

# 2. Install dependencies
./install.sh

# 3. Start the daemon (spawns 3 model servers)
codeyd2 start

# 4. Run a task
codey3 "add a docstring to every function in utils.py"

# 5. Enable the symbolic pipeline (optional)
export CODEY_SYMBOLIC=1
codey3 "create a fibonacci function"
```

### Enable Symbolic Reasoning

The symbolic pipeline is off by default for backward compatibility. Enable it:

```bash
export CODEY_SYMBOLIC=1

# Or add to ~/.bashrc for persistence
echo 'export CODEY_SYMBOLIC=1' >> ~/.bashrc
source ~/.bashrc
```

### OpenRouter (Cloud Fallback)

```bash
export OPENROUTER_API_KEY="sk-or-your-key"
export CODEY_BACKEND="openrouter"
python main.py "refactor my sort function"
```

---

## Commands

### Slash Commands

| Command | Description |
|---------|-------------|
| `/graph` | Show symbolic graph status (concepts, relations) |
| `/graph state` | Show all nodes and edges |
| `/graph check` | Check for logical inconsistencies |
| `/graph clear` | Clear the entire graph |
| `/rag <prompt>` | Debug RAG retrieval (shows graph + KB results) |
| `/memory-v2` | Show all 5 memory tiers |
| `/review <file>` | Run linters + optional agent fix |
| `/git` | Git status, commit, push |
| `/voice` | TTS/STT via Termux:API |

### CLI Flags

```bash
codey3 "task"                    # One-shot
codey3 --chat "task"             # Chat mode
codey3 --yolo "task"             # Skip confirmations
codey3 --fix file.py             # Auto-fix errors
codey3 --finetune                # Export training data + Colab notebook
codey3 --import-lora /path       # Import LoRA adapter
```

---

## Fine-Tuning (Colab)

Export your interaction history as `thought_trace` training data:

```bash
# Export dataset + generate Colab notebook
codey3 --finetune --ft-days 30

# Output:
#   ~/Downloads/codey-finetune/codey-finetune-combined.jsonl
#   ~/Downloads/codey-finetune/codey-finetune-qwen-coder-1.5b.ipynb
```

Each training example contains:
```json
{
  "conversations": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "create fibonacci"},
    {"role": "assistant", "content": "<tool>...</tool>"}
  ],
  "thought_trace": {
    "observation": "create fibonacci",
    "symbolic_graph": {
      "nodes": [{"id": "abc", "label": "fibonacci", "utterances": {"en": "fibonacci", "ar": "فيبوناتشي"}}],
      "edges": [{"source": "abc", "target": "def", "relation_type": "cause"}]
    },
    "utterances": {"en": "create fibonacci", "ar": "إنشاء فيبوناتشي", "es": "crear fibonacci"}
  }
}
```

### Training on Colab

1. Upload the `.jsonl` file to Colab
2. Run the generated notebook (QLoRA on Qwen2.5-1.5B-Instruct)
3. Download the LoRA adapter
4. Import: `codey3 --import-lora /path/to/adapter`

The notebook trains a **two-step objective**:
- **Step A**: Given observation → predict symbolic_graph
- **Step B**: Given symbolic_graph → predict utterances

---

## Requirements

| | |
|-|-|
| **Platform** | Termux on Android, or any Linux system |
| **RAM** | 6 GB+ available |
| **Storage** | ~6 GB (7B ~4.2 GB, 1.5B ~500 MB, embed ~80 MB) |
| **Python** | 3.12+ |
| **New in v3** | `networkx` (pure Python, no C deps) |

### Three-Model Architecture

| Model | Port | Role |
|-------|------|------|
| Qwen2.5-Coder-7B Q4_K_M | 8080 | Primary agent — coding, reasoning, tool use |
| Qwen2.5-Coder-1.5B Q8_0 | 8081 | Planner (NL → graph ops) + summarization |
| nomic-embed-text-v1.5 Q4 | 8082 | RAG retrieval encoder |

All three run as independent llama-server processes, managed by `codeyd2`.

---

## SQLite Schema

The `~/.codey-v3/state.db` database contains:

| Table | Purpose |
|-------|---------|
| `sg_concepts` | Abstract nodes with language-agnostic UUIDs |
| `sg_utterances` | Multilingual text renderings of concepts |
| `sg_relations` | Typed edges between concepts (cause, possess, agentive, spatial, temporal) |
| `sg_episodes` | Raw observations with graph snapshots |
| `longterm_embeddings` | Multilingual vector representations (384-dim) |
| `task_queue` | Background task queue |
| `action_log` | Episodic memory append-only log |

---

## Security

- Shell commands use `shlex.split()` + allowlist (no `shell=True`)
- Embedding deserialization uses `np.frombuffer()` (no pickle)
- File reads have 10MB size limit
- PID file locking with `fcntl.flock()`
- Unix socket connections verify UID
- Daemon shell blocks `python -c` and `-e`/`-exec` flags
- All data stays on device — no telemetry, no cloud calls by default

See [docs/security.md](docs/security.md) for full details.

---

## Documentation

| Guide | Contents |
|-------|----------|
| [Installation](docs/installation.md) | Requirements, one-line install, manual setup |
| [Commands](docs/commands.md) | Full CLI reference |
| [Configuration](docs/configuration.md) | Config, model tuning, thermal settings |
| [Architecture](docs/architecture.md) | System diagram, memory tiers, project structure |
| [Knowledge Base](docs/knowledge-base.md) | RAG setup, indexing, skill repos |
| [Fine-tuning](docs/fine-tuning.md) | Export, Colab training, import adapter |
| [Pipeline](docs/pipeline.md) | Training data pipeline |
| [Security](docs/security.md) | Risks, mitigations, hardening |
| [Troubleshooting](docs/troubleshooting.md) | Common issues, performance |

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes and run tests: `pytest tests/ -v`
4. Submit a pull request

Bug reports, security disclosures, and hardening contributions are especially welcome.

---

## Acknowledgments

- [llama.cpp](https://github.com/ggerganov/llama.cpp) — efficient on-device LLM inference
- [Qwen](https://huggingface.co/Qwen) — Qwen2.5-Coder models
- [nomic-ai](https://huggingface.co/nomic-ai) — nomic-embed-text embedding model
- [NetworkX](https://networkx.org/) — symbolic graph engine
- [sentence-transformers](https://www.sbert.net/) — multilingual embeddings
- [Codey v1](https://github.com/Ishabdullah/Codey) — the original session-based agent

---

MIT License

---

*If Codey helps you code on the go, consider starring the repo — it helps other Android developers find this project!*
