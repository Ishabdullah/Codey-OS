# Configuration

## Daemon Config

Default location: `~/.codeyOS/config.json`

Generate with: `codeydOS config`

`CODEY_STATE_DIR` must be an absolute directory. Effective daemon
`pid_file`, `socket_file`, and `log_file` values must also be absolute after
a leading `~/` is expanded. Values such as `./state`, `$HOME/state`, and
bare relative paths are refused; environment variables inside path values are
not expanded. The service tools do not guess a previous working directory,
migrate relative records, or scan for a daemon started under an invalid path.
Correct the configured value to its absolute location before attempting to
stop such a daemon.

```json
{
  "daemon": {
    "pid_file":    "~/.codeyOS/codeyOS.pid",
    "socket_file": "~/.codeyOS/codeyOS.sock",
    "log_file":    "~/.codeyOS/codeyOS.log",
    "log_level":   "INFO"
  },
  "tasks": {
    "max_concurrent":  1,
    "task_timeout":    1800,
    "max_retries":     3
  },
  "health": {
    "check_interval":        60,
    "max_memory_mb":         1500,
    "stuck_task_threshold":  1800
  },
  "state": {
    "db_path":                    "~/.codeyOS/state.db",
    "cleanup_old_actions_hours":  24
  }
}
```

The displayed `state.db_path` key is currently documentary only; the live
state store does not read it. Use `CODEY_STATE_DIR` to select the state root.

---

## Model Config

Edit `utils/config.py` to tune inference behavior.

```python
MODEL_CONFIG = {
    "n_ctx":          32768,   # Context window
    "n_threads":      4,       # CPU threads (auto-reduced under thermal load)
    "n_gpu_layers":   0,       # GPU offload layers (0 = CPU only)
    "temperature":    0.7,
    "max_tokens":     2048,    # Max response length
    "repeat_penalty": 1.1,
    "top_p":          0.8,
    "top_k":          20,
    "batch_size":     1024,
    "kv_type":        "q4_0", # KV cache quantization
}
```

---

## Planner Config

Task planning and conversation summarization run on the primary Qwen3.5-4B server (port 8080); there is no separate planner model.

```python
PLANNER_TEMPERATURE = 0.2   # Low temperature keeps plans focused
PLANNER_MAX_TOKENS  = 256   # Enough headroom for 5 clean steps
```

The planning call has a **3-minute outer timeout** (`asyncio.wait_for`, 180 s) and a **2 min 45 s HTTP timeout** (165 s) so the HTTP call always resolves before the outer timeout fires.

---

## Context Management Config

These values live in `core/summarizer.py` and control when and how conversation history is compressed.

| Setting | Value | Meaning |
|---------|-------|---------|
| `SUMMARIZE_THRESHOLD_PCT` | 0.55 | Trigger compression when context hits 55% |
| `DROP_TARGET_PCT` | 0.40 | Drop turns until usage falls to 40% |
| `MICRO_SUMMARY_MSG_LIMIT` | 2000 | Max chars per message fed to the summarizer |

**Pinned messages** (never dropped): anything containing `write_file`, `patch_file`, `[ERROR]`, `[PATCH_FAILED]`, `[BLOCKED]`, `[CONVERSATION SUMMARY]`, `Tool error:`, or `shell`.

---

## Thermal Management Config

```python
THERMAL_CONFIG = {
    "enabled":                  True,
    "warn_after_sec":           300,    # 5 min → log warning
    "reduce_threads_after_sec": 600,    # 10 min → drop to 2 threads
    "min_threads":              2,
    "temp_critical":            90,     # °C — skip recursion entirely
    "temp_warn":                75,     # °C — cap recursion depth to 1
    "batt_critical":            5,      # % — skip recursion if not charging
    "batt_low":                 15,     # % — cap recursion depth to 1
}
```

---

## Recursive Inference Config

```python
RECURSIVE_CONFIG = {
    "enabled":               True,
    "max_depth":             1,     # 1 = draft → critique → refine (3 calls total)
    "quality_threshold":     0.7,   # Skip refinement if self-score >= 7/10
    "recursive_for_writes":  True,
    "recursive_for_plans":   True,
    "recursive_for_qa":      False, # Never recurse on Q&A
    "critique_budget":       512,   # Max tokens for critique response
    "retrieval_budget":      1200,  # Max chars of KB context in refine prompt
}
```

---

## Retrieval Config

```python
RETRIEVAL_CONFIG = {
    "enabled":            True,
    "kb_path":            "~/Codey-OS/knowledge",
    "semantic_search":    True,
    "max_chunks":         4,
    "budget_chars":       2400,    # ~600 tokens of retrieved content per call
    "semantic_threshold": 0.3,     # Minimum cosine similarity
}
```

---

## Agent Config

Key agent behavior settings in `utils/config.py`:

```python
AGENT_CONFIG = {
    "max_steps":     10,    # Max tool-call steps per task
    "confirm_shell": True,  # Prompt user before every shell command
    "yolo":          False, # Skip all confirmation prompts
}
```

---

## Environment Variable Overrides

Any model path or port can be overridden without editing `config.py`:

| Variable | Default | Notes |
|----------|---------|-------|
| `CODEY_MODEL` | `~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf` | |
| `CODEY_EMBED_MODEL` | `~/models/nomic-embed/nomic-embed-text-v1.5.Q4_K_M.gguf` | |
| `CODEY_PLANNER_MODEL` | `~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf` | Same file as `CODEY_MODEL`; no separate planner model or server exists. Read only as `PLANNER_MODEL_PATH` by LoRA import/rollback (`core/lora_import.py`) |
| `CODEY_PRIMARY_PORT` | `8080` | |
| `CODEY_EMBED_PORT` | `8082` | |
| `CODEY_LLAMA_SERVER` | Auto-detected from PATH or `~/llama.cpp/build/bin/llama-server` | |
| `CODEY_PRIMARY_MMAP` | `1` (enabled) | Deprecated fallback: `CODEY_7B_MMAP` (the new name wins if both are set) |
| `CODEY_PRIMARY_MLOCK` | `0` (disabled) | Deprecated fallback: `CODEY_7B_MLOCK` (the new name wins if both are set) |
| `CODEY_BACKEND` | `local` | Coder backend: `local`, `openrouter`, `unlimitedclaude` |
| `CODEY_BACKEND_P` | `local` | Planner backend (independent of coder backend) |
