# Command Reference

## Daemon Manager — `codeydOS`

| Command | Description |
|---------|-------------|
| `codeydOS start` | Start all daemons in the background |
| `codeydOS stop` | Stop all daemons cleanly |
| `codeydOS status` | Show daemon status, uptime, and model state |
| `codeydOS restart` | Restart all daemons |
| `codeydOS reload` | Send hot-reload signal (SIGUSR1) without downtime |
| `codeydOS config` | Write a default config file to `~/.codeyOS/config.json` |

---

## CLI Client — `codeyOS`

| Command | Description |
|---------|-------------|
| `codeyOS "prompt"` | Send a task to the running daemon, or run standalone if no daemon is active |
| `codeyOS status` | Show full system status |
| `codeyOS task list` | List recent tasks and their state |
| `codeyOS task <id>` | Get full details of a specific task |
| `codeyOS cancel <id>` | Cancel a pending or running task |
| `codeyOS --daemon` | Run in foreground daemon mode (for debugging) |

### CLI Flags

These are `main.py`'s own flags. `codeyOS` passes prompt arguments through
to `main.py` unfiltered in its direct/interactive mode, so all of the
below work identically via `codeyOS` or `python main.py` directly —
`main.py` is the advanced/direct-invocation interface when you need a
flag not otherwise surfaced (e.g. `--init`, `--tdd`, `--fix`).

| Flag | Description |
|------|-------------|
| `--yolo` | Skip all confirmations |
| `--allow-self-mod` | Enable self-modification with checkpoint enforcement |
| `--threads N` | Override CPU thread count |
| `--ctx N` | Override context window size |
| `--read <file>` | Pre-load a file into context before starting |
| `--init` | Generate `CODEY.md` for the current project and exit |
| `--fix <file>` | Run a file and auto-fix any errors |
| `--tdd <file>` | TDD mode — run tests and iterate until they pass |
| `--tests <file>` | Test file for --tdd mode |
| `--no-resume` | Start a fresh session (ignore saved history) |
| `--clear-session` | Clear saved session |
| `--plan` | Force planning mode for complex tasks |
| `--no-plan` | Disable orchestration and planning |
| `--chat` | Start directly in interactive chat mode |
| `--version` | Print version information |
| `--session <id>` | Resume a specific session ID |
| `--no-peer` | Disable peer CLI auto-discovery |
| `--import-lora <path>` | Import a LoRA adapter from a given path |
| `--finetune` | Run synthetic finetune job generation |
| `--ft-days <n>` | Days of history to use for finetuning |
| `--ft-model <name>` | Model base name for finetuning |
| `--ft-output <dir>` | Output directory for finetune job |
| `--ft-quality <q>` | Minimum quality score filter for finetuning |
| `--lora-merge` | Merge LoRA weights into base model |
| `--lora-model <path>` | Target model for LoRA operations |
| `--lora-quant <q>` | Quantization format for LoRA output |

---

## In-Session Slash Commands

### Files & Context

| Command | Description |
|---------|-------------|
| `/read <file>` | Load a file into the current context |
| `/diff [file]` | Show what Codey changed in this session |
| `/undo [file]` | Restore a file to its previous version |
| `/search <pattern>` | Grep across all project files |
| `/context` | Show which files are currently loaded |
| `/clear` | Clear conversation history and session state |
| `/summarize` | Compress conversation history to save tokens |
| `/unread <file>` | Remove a file from the current context |
| `/cwd <path>` | Change the working directory |
| `/ignore <path>` | Add a file or directory to .codeyignore |
| `/exit` | Save session and quit |

### Project & Memory

| Command | Description |
|---------|-------------|
| `/project` | Show current project status and active workspace |
| `/init` | Initialize CODEY.md project memory |
| `/memory` | Show current CODEY.md contents |
| `/memory-status` | Show semantic memory system status |
| `/memory-v2` | Show RAG/Knowledge Base status |
| `/sessions` | List saved sessions |
| `/load <id>` | Load a saved session |
| `/graph` | Show import graph or project structure |

### Git

| Command | Description |
|---------|-------------|
| `/git` | Show git status |
| `/git branches` | List all branches (current highlighted) |
| `/git branch <name>` | Create and switch to a new branch |
| `/git checkout <name>` | Switch branch with confirmation prompt |
| `/git merge <branch>` | Merge with conflict detection and resolution flow |
| `/git commit` | Generate an AI commit message from diff — you approve before commit |
| `/git commit "msg"` | Commit with an exact message |
| `/git diff` | Show the current diff |
| `/git push` | Push to remote |
| `/git conflicts` | List all conflicted files |

### Code Quality

| Command | Description |
|---------|-------------|
| `/review <file.py>` | Lint with all available tools and offer agent fix |

### Knowledge Base

| Command | Description |
|---------|-------------|
| `/rag <prompt>` | Show what the KB would retrieve and inject for a given prompt |

### Voice

| Command | Description |
|---------|-------------|
| `/voice` | Show voice status |
| `/voice on` / `/voice off` | Enable or disable TTS + STT |
| `/voice listen` | Speak one task and send it to the agent immediately |
| `/voice rate <n>` | Set TTS speech speed (default 1.0) |
| `/voice pitch <n>` | Set TTS pitch (default 1.0) |
| `/voice speak <text>` | Test TTS with a specific phrase |

### Peer CLI Escalation

| Command | Description |
|---------|-------------|
| `/peer` | List available peer CLIs and their status |
| `/peer <name> <task>` | Call a specific peer CLI directly |
| `/peer <task>` | Auto-pick the best peer CLI for the task |

### System

| Command | Description |
|---------|-------------|
| `/learning` | Show learning system status and learned preferences |
| `/status` | Full system state: tasks, memory, tokens, thermal |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CODEY_MODEL` | Override the primary model path |
| `CODEY_EMBED_MODEL` | Override the embedding model path |
| `CODEY_7B_MMAP=0` | Disable memory-mapped weights (use if RAM is tight) |
| `CODEY_7B_MLOCK=1` | Lock weights in RAM (prevents paging under pressure) |
| `CODEY_THREADS` | Override CPU thread count |
| `CODEY_LINTER` | Override linter: `ruff`, `flake8`, or `mypy` |
| `CODEY_PLANND_PORT` | Override the planner/summarizer model port (default 8081) |
| `CODEY_EMBED_PORT` | Override the embedding model port (default 8082) |
| `ALLOW_SELF_MOD=1` | Enable self-modification (alternative to `--allow-self-mod`) |
