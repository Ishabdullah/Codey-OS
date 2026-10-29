# Troubleshooting

## Common Issues

### Daemon won't start

```bash
# Remove a stale PID file left by a crash
rm -f ~/.codeyOS/codeyOS.pid

# Check the log for the actual error
cat ~/.codeyOS/codeyOS.log

# Restart cleanly
codeydOS restart
```

### Socket connection failed

```bash
# Confirm the daemon is running
codeydOS status

# Confirm the socket exists with correct permissions
ls -la ~/.codeyOS/codeyOS.sock
# Expected: srw------- (0600, owner only)
```

### Model not found

```bash
ls -la ~/models/qwen3.5-4b-instruct/
ls -la ~/models/nomic-embed/
```

Check that the filenames match the paths in `utils/config.py`, or set `CODEY_MODEL` and `CODEY_EMBED_MODEL` environment variables to the correct paths.

### High memory usage

```bash
codeydOS status   # Check RAM and task queue

codeydOS restart  # Clears working memory
```

If the primary model alone is using a lot of RAM, verify that `CODEY_PRIMARY_MMAP=1` is set (default; the older name `CODEY_7B_MMAP` is still honoured as a deprecated fallback). Memory-mapped weights only load touched pages into RAM.

### Planner / summarizer not responding

Planning and summarization use the primary model server on port 8080; it may have failed to start or crashed.

```bash
cat ~/.codeyOS/codeyOS.log        # Check main daemon log
cat ~/.codeyOS/llama-server.log  # Check llama-server log

codeydOS restart                   # Restart all daemons
```

There is no separate planner server (port 8081 is retired). If the primary server on port 8080 is unreachable, task planning falls back to heuristic decomposition and context compression skips the micro-summary step. The agent continues working normally.

### Peer CLI crashes on startup

On Android ARM64, some CLIs bundle native Node.js modules (e.g., `node-pty`) that have no ARM64 prebuilt. Codey detects this automatically at startup and excludes broken CLIs from the available list. No manual configuration is needed.

To check which peers are available:

```bash
codeyOS   # then type /peer
```

---

## Performance Reference

| Metric | Value |
|--------|-------|
| Primary model (all generation roles) | Qwen3.5-4B Q4_K_M |
| Embedding model | nomic-embed-text-v1.5 Q4_K_M |
| RAM (idle) | ~200 MB |
| RAM (primary model loaded) | not re-measured for this doc; see `core/resource_gate.py` and live measurements |
| RAM (embed loaded) | ~80 MB |
| Context window | see `utils/config.py` (`CODEY_N_CTX`) |
| Max response tokens | 2,048 |
| Speed | not re-measured for this doc |
| Inference backend | `/v1/chat/completions` over localhost HTTP |
| Backend overhead | ~400–600 ms per call |

---

## Known Limitations

| Limitation | Impact | Status |
|------------|--------|--------|
| HTTP API overhead | ~400–600 ms per inference call | Single reliable HTTP backend; direct socket path not available on Android |
| CPU-only inference | ~7–8 t/s at 4 threads on S24 Ultra | Thermal management prevents sustained throttling |
| No NPU / GPU acceleration | Cannot offload to device accelerator | `n_gpu_layers=0` — CPU path only on Android |
| `watchdog` optional | Background file monitoring disabled without it | `pip install watchdog` to enable |
| Single-device only | State is not synced across devices | Intentional — local privacy by design |
| Peer CLIs with `node-pty` | CLIs that bundle ARM64-incompatible native modules crash on Android | Auto-detected and excluded at startup |
| No encrypted memory | `~/.codeyOS/` stored in plaintext | Encryption planned for a future release |

---

## Logs Reference

| Log file | Contents |
|----------|----------|
| `~/.codeyOS/codeyOS.log` | Main daemon log |
| `~/.codeyOS/plannd-llama.log` | llama-server log (legacy planner server; no longer started) |
| `~/.codeyOS/embed-server.log` | nomic-embed llama-server log |
