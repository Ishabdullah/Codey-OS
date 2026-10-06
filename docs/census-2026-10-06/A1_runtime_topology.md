# CENSUS A1 — Runtime entry points, service topology, model loading, resource/thermal subsystems

Read-only static census of `/data/data/com.termux/files/home/Codey-OS`, 2026-10-06.
No service, daemon, or model was started. `~/.codeyOS/restoricon.db` was never opened.
All paths below are repo-relative unless absolute. Every claim cites `file:line`.

Status vocabulary: IMPLEMENTED (reachable from a real entry point + does its job),
PARTIAL, DORMANT (no caller path from any entry point), DOCS-ONLY, MISSING.

---

## (a) Entry-point map

### Shell entry points (all resolve their own repo root from `$BASH_SOURCE`)

| Entry point | Lines | What it does |
|---|---|---|
| `codey` | `codey:24-73` | **The real unified CLI.** Sources `lib/service_manager.sh:24`, dispatches `start`/`stop`/`status`/`restart`/`logs`/`config`/`help`; **any unrecognized arg falls through to `start_all_services` + `exec bash codeyOS "$@"`** (`codey:67-71`). |
| `codey-start` | `codey-start:15-22` | Sources `service_manager.sh`, calls `start_all_services()`, then `exec bash codeyOS "$@"`. Thin wrapper over what `codey` (no-arg) already does. |
| `codey-stop` | `codey-stop:15-17` | Sources `service_manager.sh`, calls `stop_all_services()`. |
| `codeyOS` | `codeyOS:9-410` | **Interactive CLI client.** If daemon PID+socket live (`codeyOS:18-39`), writes a throwaway Python script to `$HOME/.codeyOS/socket_XXXX.py` via `mktemp` and talks to the Unix socket (`codeyOS:46-105`). `--daemon` passes through to `main.py:main()` (`codeyOS:108-122`). `status` does a `health` socket round-trip (`codeyOS:125-200`). |
| `codeydOS` | `codeydOS:25-339` | **Daemon manager.** `start`/`stop`/`status`/`restart`/`reload`/`config`. Writes a temp launcher that does `from core.daemon import main; main()` (`codeydOS:186-196`), spawns it with `nohup python3` (`codeydOS:199`). |
| `codey-metrics` | `codey-metrics:14-16` | `exec python3 -m telemetry.cli "$@"` from repo root. A real, separate entry point. |
| `install.sh` | `install.sh:586-630` | Installer; see below. |
| `setup.sh`, `setup_repo.sh` | top-level | Legacy; not referenced by `install.sh:586-630` or any service script. **DORMANT** (searched: `grep -rn "setup.sh\|setup_repo.sh" --include=*.sh --include=*.py` → only self-references). |

### Python entry points

| Entry point | Evidence |
|---|---|
| `main.py` | `main.py:2197` lines; the TUI/one-shot agent CLI. Reached via `codeyOS --daemon` (`codeyOS:115`) and by direct `python3 main.py`. |
| `core/daemon.py:main()` | `core/daemon.py:2305`; reached only via `codeydOS start`'s temp launcher (`codeydOS:194`). |
| `restoricon_core/api/server.py` | `__main__` block at `restoricon_core/api/server.py:307-332`; launched as `python3 -m restoricon_core.api.server` by `service_manager.sh:247`. |
| `telemetry/cli.py` | via `codey-metrics:16`. |
| `core/setup_litestream.py` | **Real startup entry point** — invoked at `service_manager.sh:559` to generate `~/.codeyOS/litestream.yml`. |
| `core/backup_secrets.py` | **Real startup entry point** — one-shot `timeout 60 python3` at `service_manager.sh:565`; failure warns but does not block startup (`service_manager.sh:566-569`). |
| `core/backup_documents.py --daemon` | Long-lived service, `service_manager.sh:807`. |
| `core/daemon_config.py:create_default_config()` | via `codeydOS config` (`codeydOS:319-321`). |
| `core/setup_dr_key.py` | Referenced only in an operator hint string, `service_manager.sh:568`, and `install.sh:466` (`setup_dr_escrow`). Manual. |

### Remaining `__main__` modules (full enumeration)

The shell-script scan above cannot see Python entry points, so these were enumerated separately
with `grep -rln "__main__" --include=*.py .` minus `./tests/`, `./ccos/tests/`, `./ccos/demo_*`.
Beyond the ones already tabled:

| Module | Wired to a service? | Note |
|---|---|---|
| **`tools/ensure_model_cli.py`** | **Yes — see (b)** | `main()` at `:89` calls `core.loader_v2.get_loader()` at `:92`. Directly in A1 scope: a second, non-daemon path that loads the model. |
| **`tools/release_model_cli.py`** | **Yes — see (b)** | `main()` at `:69` calls `core.daemon.send_command()` at `:73, 77` — a thin socket client for `release_model_slot`. |
| `tools/provision_ai_agent_auth.py`, `tools/adb_confound_monitor.py` | No | Operator utilities; not invoked by any service script. |
| `pipeline/run.py`, `pipeline/synthetic.py`, `pipeline/transformation/rules.py` | No | Training-data pipeline, run manually. Not started by `start_all_services`. |
| `bench/promote.py` | No | The promotion-gate runner (CLAUDE.md rule 1). Manual by design. |
| `restoricon_core/migrate_aigentik.py`, `restoricon_core/backfill_wo_351695937.py` | No | One-shot migration/backfill scripts. |
| `ccos/core/skill_recombiner.py` | **Not an entry point** | The `__main__` at `:459` is inside a *generated code string* this module emits, not a guard on the module itself. Its self-improvement path is gated off by default (`:528`, `CODEY_SELF_IMPROVE`). |
| `.live_verify_scratch/*.py` (7 files) | No | Live-verification leftovers. |

### Startup order (`start_all_services`, `lib/service_manager.sh:891-899`)

```
1. start_daemon      → bash codeydOS start                (service_manager.sh:204)
2. start_restoricon  → python3 -m restoricon_core.api.server (service_manager.sh:247)
3. start_aigentik    → node index.js in ~/Codey-Aigentik   (service_manager.sh:411)
4. start_cloudflare  → cloudflared tunnel run --token ...   (service_manager.sh:733)
5. start_litestream  → setup_litestream.py, backup_secrets.py, then litestream replicate (service_manager.sh:559,565,626)
6. start_backup_docs → python3 backup_documents.py --daemon (service_manager.sh:807)
```

`stop_all_services` is the exact reverse (`service_manager.sh:901-911`). There is **no dependency
ordering or readiness gate** between steps: each is a fire-and-forget `nohup ... &` followed by
`sleep 0.5` + `kill -0` (e.g. `service_manager.sh:250-258`). A `kill -0` 0.5s after fork proves
the process forked, not that it bound its port or finished loading.

### PID / lock / socket file inventory

All under `$DAEMON_DIR = ${CODEY_STATE_DIR:-$HOME/.codeyOS}` (`service_manager.sh:11`).

| File | Writer | Notes |
|---|---|---|
| `codeyOS.pid` | `codeydOS:209-210` (atomic `.tmp`+`mv`) **and** `core/daemon.py:146 write_pid_file()` / `:2155` | Deliberately double-written; the shell write lands first to close a start-race during the 15–40s model load (`codeydOS:202-208`). |
| `codeyOS.sock` | `core/daemon.py:705` `asyncio.start_unix_server`, chmod `0o600` at `:708` | Unlinked before bind (`:703`) and on shutdown (`:722`). |
| `restoricon-api.pid` | `service_manager.sh:249` | |
| `aigentik.pid` | `service_manager.sh:413` | |
| `aigentik.lock` | `service_manager.sh:333-346` | `flock -n` on fd 200, non-blocking; closed on the spawn line with `200>&-` (`service_manager.sh:411`) so the long-lived node child does not hold the lock for its lifetime. |
| `cloudflared.pid` | `service_manager.sh:735` | |
| `litestream.pid` | `service_manager.sh:628` | |
| `backup-docs.pid` | `service_manager.sh:809` | |
| `llama-server-8080.pid` | `core/loader_v2.py:807-813` (atomic `.tmp`+`os.rename`) | Consumed by `codeydOS:140-158 kill_llama_server_gracefully()`. |
| `llama-server-8080.lock` | `core/loader_v2.py:564` | Per-port start lock. |
| **(no PID file for the embed server)** | — | See (f) DORMANT/gap findings. |

Rule 3 compliance: every kill path reads a tracked PID or uses two-factor
cwd+cmdline-token matching (`service_manager.sh:145-195`); the `$3`-empty cwd-only
path is documented as test-only (`service_manager.sh:140-144`). No `pkill -f` anywhere in
`service_manager.sh`, `codeydOS`, `codey*`.

---

## (b) Service topology + ports

When fully up (`start_all_services` + a daemon that has loaded the model + an `infer()` call):

| Process | Bind | Who starts it | Evidence |
|---|---|---|---|
| Codey-OS daemon (`core/daemon.py`) | **Unix socket only**, `~/.codeyOS/codeyOS.sock` | `codeydOS start` | `core/daemon.py:705` |
| `llama-server` (primary, Qwen3.5-4B) | `127.0.0.1:8080` | `core/loader_v2.py:799` `subprocess.Popen` | `utils/config.py:16` `PRIMARY_SERVER_PORT`, `loader_v2.py:44-45` |
| `llama-server` (embed, nomic-embed-text-v1.5) | `127.0.0.1:8082` | `core/embed_server.py:139-158`, started eagerly by the daemon (`core/daemon.py:1134-1136`) and lazily by `core/inference.py:101-105` | `utils/config.py:28` `EMBED_SERVER_PORT` |
| Restoricon Core API | `127.0.0.1:8770` (ThreadingHTTPServer) | `service_manager.sh:247` | `restoricon_core/api/server.py:36-38, 238` |
| ↳ `EstimateExpirySweepThread` | in-process thread | `restoricon_core/api/server.py:287` | |
| Codey-Aigentik | **no TCP listener** | `service_manager.sh:411`, `node index.js` | see below |
| `cloudflared` | outbound tunnel, no local bind | `service_manager.sh:733` | token from `config.json:3` |
| `litestream replicate` | no bind | `service_manager.sh:626` | config `~/.codeyOS/litestream.yml` |
| `backup_documents.py --daemon` | no bind | `service_manager.sh:807` | |

### Who talks to what

- `codeyOS` (shell) → daemon Unix socket, JSON `{"cmd":..., "data":...}` (`codeyOS:61`, dispatched at `core/daemon.py:645-667`). Handlers: `ping`, `command`, `status`, `health`, `task`, `cancel`, `release_model_slot` (`core/daemon.py:199, 203, 319, 375, 420, 436, 486`).
- `main.py` / `core/agent.py` → `core/inference_v2.infer()` → `core/inference_hybrid` (local) or `core/inference_openrouter` (remote), selected by `is_remote_backend()` at `core/inference_v2.py:44-61`; `core/inference.infer()` is the legacy HTTP fallback (`core/inference_v2.py:196`).
- Local inference → `http://127.0.0.1:8080/v1/chat/completions`.
- Retrieval/KB → `http://127.0.0.1:8082/v1/embeddings`, BM25 keyword fallback when unhealthy (`core/inference.py:106-107`).
- Restoricon API (`restoricon_core/api/routes.py:414-490`) imports `core.resource_gate` directly and runs its own AI-completion proxy through the same context-budget gate — the Core API process is a **second** consumer of the model server, in-process with the business API.
- Restoricon API also imports `ccos.core.plugin_manager` (`restoricon_core/api/routes.py:533`).
- **Aigentik (Node) drives the model's lifecycle by shelling out to Python.** Verified from the
  Aigentik side, not just the Python docstring:
  - `~/Codey-Aigentik/index.js:201` — `execSync('curl -s http://127.0.0.1:8080/health')`
  - `~/Codey-Aigentik/index.js:228` — `execSync("python3 .../Codey-OS/tools/ensure_model_cli.py")`
  - `~/Codey-Aigentik/index.js:1740` — `execSync("python3 .../Codey-OS/tools/release_model_cli.py")`
  So a Node process **loads and unloads the 2.7 GB model** via two absolute-path Python
  subprocesses. `ensure_model_cli.py` goes straight to `core.loader_v2.get_loader()` (`:92`),
  i.e. it loads the model **in its own short-lived process**, not through the daemon;
  `release_model_cli.py` goes through the daemon socket (`:73, 77`). Asymmetric by design
  (`tools/release_model_cli.py:14` documents the socket-client shape), but it means the load path
  has a second owner outside the daemon. Both are `stdio: 'ignore'`, so failures are invisible to
  Aigentik. This is the cross-process edge most likely to interact badly with the RAM discipline in
  CLAUDE.md rule 2, and it is reached from `start_all_services` step 3.
- `~/Codey-Aigentik/index.js` also reaches the Core API at `127.0.0.1:8770/api/v1/...`
  (asserted throughout `~/Codey-Aigentik/tests/comms-write-through.test.js:36-200`).

**No other listener exists.** Verified rather than assumed: `grep -n "bind(\|listen(\|
start_unix_server\|serve_forever\|AF_INET\|Popen" core/planner_service.py core/planner_client.py
core/peer_shell.py core/peer_cli.py core/background.py core/daemon.py` → the *only* hits are
`core/daemon.py:705` (the Unix socket) + `:714` (`serve_forever`) and three `subprocess.Popen`
calls in `core/peer_shell.py:262, 319, 524`. Despite the client/server naming,
**`core/planner_service.py` and `core/planner_client.py` bind and spawn nothing** — consistent
with the port-8081 `plannd` retirement (`utils/config.py:471-495`). `core/daemon.py` itself
contains **no `Popen`**: it spawns `llama-server` only indirectly through
`core/loader_v2.py:799`, and the embed server through `core/embed_server.py`.

### Dashboard / GUI surface

**There is no separate GUI server.** The dashboard is served by the Core API process on
port **8770**, not 8888:

```
restoricon_core/api/server.py:320-323
  • Quote Surface:   http://host:port/quote
  • Admin Dashboard: http://host:port/admin
  • Customer Portal: http://host:port/portal
  • REST API Base:   http://host:port/api/v1
```

HTML for these lives in `restoricon_core/api/web_surfaces.py` (574 KB single file).

**`config.json:11-14` declares `"gui": {"host": "127.0.0.1", "port": 8888}` and nothing in
the repo reads it.** Searched: `grep -rn "8888\|get_gui_config\|\"gui\"\|'gui'" --include=*.py
--include=*.sh .` → **zero hits** outside `config.json` itself. No `get_gui_config()` function
exists in `utils/config.py` (contrast `get_restoricon_api_config` at `:683` and
`get_aigentik_config` at `:749`).

This is a **leftover from a deliberately removed subsystem**, not a never-built one. A `gui/`
directory with `gui/start.sh` on port 8888 existed and was deleted: `git log --diff-filter=D --
gui/` gives `65c9f10 feat(gui)!: remove the browser GUI; resource gate loses its fail-open
signal` and `63ab3df Phase 3 closeout: delete gui/start.sh and ccos_main.py`. `gui/` is absent
from the tree today. The removal was handled correctly inside `core/resource_gate.py` — the
GUI half of the interactivity signal was *deleted* rather than left as a vestigial branch,
with an explicit rationale that the old `is_gui_client_connected()` would have failed open
forever on a stale `gui-clients.count` with no `gui-server.pid` to cross-check
(`core/resource_gate.py:3855-3856, 3969-3980`). So the only thing missed in that sweep is the
`config.json` block. Verdict: **stale config leftover**; the real control surface is `/admin`
on 8770.

`core/dashboard_data.py` is a *terminal* renderer (`main.py:10` imports `get_render_text`), not a web surface.

### Aigentik port is dead twice over

`a_port` is parsed at `service_manager.sh:285` (`start_aigentik`), `:436` (`stop_aigentik`),
`:496` (`status_aigentik`) and **never referenced again in any of the three functions** — the
launch command is built purely from `svc_detect_entrypoint_script` (`:295-297`). Independently,
`~/Codey-Aigentik/index.js` contains **no `listen(`** call (`grep -rn "listen(\|PORT\|8000"
~/Codey-Aigentik/index.js` → no bind hits), and `~/Codey-Aigentik/config.json` has only
`imap_port: 993` / `smtp_port: 587`. So `AIGENTIK_PORT` / `config.json:17 aigentik.port=8000`
is read, discarded, and would describe nothing if it weren't.

Entrypoint resolution, verified on-device: `~/Codey-Aigentik` contains `index.js` and
`start.sh` but none of `main.py`/`app.py`/`server.py`/`run.sh`, so the candidate order at
`service_manager.sh:99` selects **`index.js`** → launch `node index.js`
(`service_manager.sh:111-116`), proc filter `node` (`:124-133`), orphan token `index.js`.
Launch command and kill token agree.

---

## (c) Model-loading path with exact flags

### Call path (concrete, from an entry point)

```
codeydOS start                                  (codeydOS:204 via service_manager.sh:204)
  → temp launcher: from core.daemon import main (codeydOS:194)
    → core/daemon.py:main()                     (:2305)
      → _main_loop()                            (:1088)
        → _watchdog_check_model()               (:984)
          → loader.ensure_model()               (:1042)
            → core/loader_v2.py ModelLoader.load_primary()
              → rg.reserve_slot(spec, port=PRIMARY_SERVER_PORT, meminfo=gate_meminfo)  (loader_v2.py:1450)
              → LlamaServer.start() → _spawn_locked()                                   (loader_v2.py:660)
                → subprocess.Popen(cmd, preexec_fn=os.setsid)                           (loader_v2.py:799-804)
              → rg.mark_resident(slot_id, pid=pid)                                      (loader_v2.py:211)
```

Interactive path: `main.py` → `core/inference_v2.infer()` → `core/inference_hybrid` →
(if no server) `core/inference.py:_start_server()` retry loop (`core/inference.py:63-73`).

### Exact spawn argv (`core/loader_v2.py:676-713`, plus `:745`)

```
<LLAMA_SERVER_BIN>
  -m <cfg.MODEL_PATH>
  --host 127.0.0.1                 # loader_v2.py:44 SERVER_HOST
  --port <self.port>               # 8080
  -c <self.n_ctx>
  -t 6                             # MODEL_CONFIG["n_threads"], utils/config.py:102
  --temp 0.7                       # utils/config.py:104
  --top-p 0.8                      # :107
  --top-k 20                       # :108
  --repeat-penalty 1.1             # :106
  --n-predict 2048                 # :105 max_tokens
  --flash-attn on
  --embedding
  --pooling mean
  --jinja
  --reasoning-format deepseek
  --load-mode {mmap|mlock|mmap+mlock|none}   # loader_v2.py:734-746
```

- `--load-mode` is derived from the two independent booleans `QWEN_MMAP`
  (`utils/config.py:509`, default **True**, env `CODEY_7B_MMAP`) and `QWEN_MLOCK`
  (`utils/config.py:510`, default **False**, env `CODEY_7B_MLOCK`) → default value **`mmap`**.
  Must be two argv elements; `--load-mode=value` is rejected by this build
  (`loader_v2.py:732-733`). This is the NEW-754 launch-blocking fix (commit `b5b805a`).
- `--reverse-prompt` was deliberately removed as vestigial; stop sequences are enforced per
  request via the JSON `"stop"` field in all three inference paths (`loader_v2.py:715-725`).
- The spawned argv is captured to `self.last_argv` (`loader_v2.py:756`) for telemetry
  (`loader_v2.py:1295`).
- Before the real spawn, a `--version` probe is written as the first lines of
  `~/.codeyOS/llama-server.log` (`loader_v2.py:776-792`), to make binary drift visible.
- SIGINT is masked across the whole spawn setup window (`loader_v2.py:671`, unblocked at `:815`) — NEW-9.
- Health wait: 120 × 0.5 s = 60 s (`loader_v2.py:820`).
- Process group: `preexec_fn=os.setsid` (`loader_v2.py:803`), so the group can be killed as a unit.

### Binary resolution (`utils/config.py:40-49`)

Priority: `$CODEY_LLAMA_SERVER` → `~/llama.cpp/build/bin/llama-server` if executable →
`shutil.which("llama-server")` → the source-build path anyway. Two binaries can exist on this
device and drift (`loader_v2.py:763-768`).

### Model path and current default model — verified from the artifact, not docs

`utils/config.py:8-13`:
```python
MODEL_PATH = Path(os.environ.get("CODEY_MODEL",
    Path.home() / "models" / "qwen3.5-4b-instruct" / "Qwen3.5-4B-Q4_K_M.gguf"))
```
File exists: `2,740,937,888` bytes, dated 2026-08-20.

`MODEL_PATH` is deliberately **not** imported as a bound name into `loader_v2` — it reads
`cfg.MODEL_PATH` fresh each call so `core/lora_import.py`'s hot-swap is visible
(`loader_v2.py:33-41`, NEW-84).

GGUF header dumped directly (full 46-key set read, not a filtered grep — CLAUDE.md rule 12):

```
general.architecture              = qwen35
general.name                      = Qwen3.5-4B      (quantized_by: Unsloth, apache-2.0)
general.tags                      = ['unsloth', 'image-text-to-text']
qwen35.block_count                = 32
qwen35.context_length             = 262144
qwen35.embedding_length           = 2560
qwen35.feed_forward_length         = 9216
qwen35.attention.head_count       = 16
qwen35.attention.head_count_kv    = 4
qwen35.attention.key_length       = 256
qwen35.attention.value_length     = 256
qwen35.rope.freq_base             = 10000000.0
qwen35.rope.dimension_count       = 64
qwen35.rope.dimension_sections    = [4 x int32]
qwen35.ssm.conv_kernel            = 4
qwen35.ssm.state_size             = 128
qwen35.ssm.group_count            = 16
qwen35.ssm.time_step_rank         = 32
qwen35.ssm.inner_size             = 4096
qwen35.full_attention_interval    = 4
tokenizer.ggml.model              = gpt2    (pre = qwen35)
tokenizer.ggml.tokens             = 248320 entries
tokenizer.ggml.eos_token_id       = 248046
general.file_type                 = 15 (Q4_K_M)
tensor count                      = 426
```

Load-bearing observations from the header:
1. **This is a hybrid SSM/attention architecture.** The `qwen35.ssm.*` keys plus
   `full_attention_interval = 4` mean only every 4th block is full attention; the rest are
   state-space. Any KV-cache sizing math that assumes 32 uniform attention layers is wrong.
   This directly matters for `core/resource_gate.py`'s cost model.
2. Native `context_length = 262144`; the configured default `n_ctx` is **65536**
   (`utils/config.py:78`), i.e. 25% of native. Overridable via `CODEY_N_CTX`, which is
   validated and raises on a non-positive value (`utils/config.py:76-88`).
3. `general.tags` includes `image-text-to-text` — the base model is multimodal, and the spawn
   argv passes no `--mmproj`. Stated as an observation, not a defect; the deployment uses it
   text-only.
4. `MODEL_CONFIG["kv_type"] = "q4_0"` (`utils/config.py:109`) **never reaches argv** — no
   `--cache-type-k`/`--cache-type-v` is passed. Already logged; `core/resource_gate.py:973-979`
   explicitly notes the dead key and says NEW_ISSUES.md has an entry. Cross-referenced here, not
   claimed as new.

### Embed-server spawn argv (`core/embed_server.py:139-158`)

```
<llama_bin> -m <EMBED_MODEL_PATH> --host 127.0.0.1 --port 8082
  -c 2048 -t 2 -b 2048 --ubatch-size 2048 --embedding --pooling mean
```
Note: **no `--load-mode`** here. If the NEW-754 flag migration applies to this binary (it is the
same binary), the embed server relies on the build's own `auto` default — a flag-set divergence
between the two spawn sites in the same repo.

### `install.sh` vs the model config

`install.sh:54-66` downloads `Qwen3.5-4B-Q4_K_M.gguf` into `~/models/qwen3.5-4b-instruct/`
from `https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf`,
and `install.sh:69` the nomic embed model. Both match `utils/config.py:8-13` and `:22-27`
exactly. `install.sh:365-384` symlinks `codey codey-start codey-stop codey-metrics codeyOS
codeydOS` — all six entry points, correctly current.

---

## (d) Resource / thermal / sysmon reachability table

Search method for every DORMANT verdict below: `grep -rn "<symbol>(" --include=*.py .` from the
repo root, then exclude `./tests/`, `./ccos/tests/`, `./ccos/demo_*`, `./bench/`, `./docs/`, and the
defining module itself. Demos and tests are **not** entry points. Import-level presence was never
accepted as evidence — every verdict below is function-call-level.

| Module / symbol | Status | Concrete call path, or what was searched |
|---|---|---|
| `core/resource_gate.py` **slot admission** — `reserve_slot` | **IMPLEMENTED, on the live model-load path** | `core/loader_v2.py:1450`: `rg.reserve_slot(spec, port=PRIMARY_SERVER_PORT, meminfo=gate_meminfo)`. The NEW-259 `port=` kwarg is present. |
| `mark_resident` | IMPLEMENTED | `core/loader_v2.py:211`, after health-confirmed spawn + a MemAvailable confirmation window (`loader_v2.py:116-118`). |
| `release_slot` | IMPLEMENTED | `core/loader_v2.py:501, 1533, 1602, 1731`; `core/embed_server.py:279`. |
| **context-budget gate** — `wait_and_reserve_context_budget` | **IMPLEMENTED, on the live inference path, 3 real call sites** | `core/inference_hybrid.py:443`; `core/plannd.py:888`; `restoricon_core/api/routes.py:420`. |
| `release_context_budget` | IMPLEMENTED | `core/inference_hybrid.py:569`; `core/plannd.py:1073`; `restoricon_core/api/routes.py:488`. |
| `is_interactive_session_active` | IMPLEMENTED | `core/daemon.py:1288, 1488`; `core/inference_hybrid.py:430`; `core/plannd.py:875`; `restoricon_core/api/routes.py:3449`. |
| `can_dispatch_task`, `get_resource_snapshot` | IMPLEMENTED | `core/daemon.py:1488`; `main.py:1995`. |
| `sample_cpu_percent`, `sample_temperature_c`, `should_trip_shutdown` | IMPLEMENTED (daemon monitor loop) | `core/daemon.py:1172, 1189, 1202`. |
| `compute_zram_compression_ratio` | IMPLEMENTED | `core/daemon.py:1426`. |
| `core/resource_bus.py` — `acquire_context_lease` / `release_context_lease` | **IMPLEMENTED (live)** | `core/resource_gate.py:4699` / `:4763`, reached from the three `wait_and_reserve_context_budget` sites above. Confirmed live by the on-disk DB: `~/.codeyOS/resource_bus.db`, 278 KB, mtime 2026-10-06 04:11. |
| `core/resource_bus.py` — `request_resource` (`:446`), `release_lease` (`:565`), `poll_queue` (`:578`), `reap_stale_records` (`:295`) | **DORMANT** | Searched `grep -rn "request_resource(\|poll_queue(\|release_lease(\|reap_stale_records(" --include=*.py .` minus `./tests/` and `core/resource_bus.py` → **zero callers**. The generic multi-resource bus API is unused; only the context-lease pair is wired. (`_reap_stale_records_locked` at `:256` *is* called internally.) |
| `core/thermal.py` — `start_inference` / `end_inference` | **PARTIAL: daemon-only** | `core/task_executor.py:23` imports them; `:332` / `:431` bracket the agent run. `task_executor` reaches a real entry point via `core/daemon.py:28` (`from core.task_executor import TaskExecutor`). **No interactive path brackets inference**: `grep` for `thermal` across `main.py`, `core/agent.py`, `core/inference*.py` → no import. So thermal duration accounting only accrues for daemon-queued tasks, never for TUI/one-shot inference. |
| `core/thermal.py` — `restart_recommended` consumer | IMPLEMENTED (daemon) | `core/loader_v2.py:1786` reads `tm.restart_recommended` inside `ensure_model()`; fails open on any exception (`loader_v2.py:1792-1796`). |
| `core/thermal.py` — `is_inference_active` | IMPLEMENTED | `core/daemon.py:564-566`, used to refuse `release_model_slot` while a task is in flight; fails **closed** (`core/daemon.py:573-575`). |
| `core/thermal.py` — `get_current_temp_c` | IMPLEMENTED | `core/resource_gate.py:492` (lazy import); `core/resource_bus.py:201`. |
| `core/thermal.py` — `ThermalManager.reset()` / `reset_thermal()` | **DORMANT (no automatic restore)** | Two separate claims, separated because one needed a full key dump (rule 12). **(i) No caller — verified:** `grep -rn "reset_thermal(\|\.reset()" --include=*.py core/ main.py ccos/` → the only hit is `ccos/plugins/system/thermal_monitor/thermal_monitor.py:81`. **(ii) No cooldown key — verified by dumping the whole dict,** not by grepping for `cooldown`. `utils/config.py:166-178` in full: `enabled: True`, `warn_after_sec: 300`, `reduce_threads_after_sec: 600`, `min_threads: 2`, `original_threads: 4`, `temp_critical: 90`, `temp_warn: 75`, `batt_critical: 5`, `batt_low: 15` — nine keys, **no cooldown/reset key**, and the last four are adaptive-recursion-depth thresholds consumed elsewhere, not throttle-restore timers. So `reset()`'s docstring reference to "after cooldown period" (`core/thermal.py:159`) names a mechanism that does not exist. Consequence: once `_reduce_threads()` fires (`core/thermal.py:135-150`, after 600 s cumulative inference) the reduced `MODEL_CONFIG["n_threads"]` is permanent for the process lifetime unless an operator invokes the CCOS plugin. Incidental: `original_threads: 4` at `:171` is immediately overwritten to 6 at `:180` from `MODEL_CONFIG`, so the literal is misleading but harmless. |
| `core/sysmon.py` — `get_monitor()` | **IMPLEMENTED, but display-only — NOT a gate** | `main.py:1678` (TUI status bar), `main.py:291` (`.stop()`), `core/recursive.py:196` (`snapshot`), `ccos/plugins/system/thermal_monitor/thermal_monitor.py:42,49`. No inference or dispatch decision consults it; `grep -n "sysmon" core/inference*.py core/loader_v2.py core/resource_gate.py` → resource_gate uses only `read_battery_status` (`:812`). |
| `core/sysmon.py` — `read_battery_status` | IMPLEMENTED | `core/resource_gate.py:812`; `core/daemon.py:1381`. |
| `core/sysmon.py` — `render_snapshot` | IMPLEMENTED | `core/dashboard_data.py:49` ← `main.py:10`. |

**Bottom line for (d):** the resource gate is genuinely live on both the model-load path and the
inference path — this is not shelfware. Thermal is live but only in the daemon process and has no
working restore. Sysmon is purely observational. The generic half of `resource_bus` is dead.

---

## (e) Observability / recovery / checkpoint

| Module | Status | Evidence |
|---|---|---|
| `core/observability.py` | **IMPLEMENTED, read-only aggregator** | Public API is only `get_state()` `:330`, `reset_state()` `:338`, `status()` `:345`. Reached from `main.py:1994` (`/status`) and `ccos/plugins/system/observability/observability.py:45-46`. `State` (`:32`) derives everything from `core/state.py`'s store, the task queue, psutil, and `DAEMON_PID_FILE` — the only writer is the `tokens_used` setter (`:58`). It records nothing itself; it is a view. Degrades without psutil (`:20-26`). |
| `core/recovery.py` | **DORMANT on every core path** | Public API `get_switcher()` `:376`, `reset_switcher()` `:384`, `recover_from_error()` `:391`, `execute_strategy()` `:404`. Searched `grep -rn "recover_from_error(\|execute_strategy(\|get_switcher()" --include=*.py .` minus `./tests/` → the **only** non-test callers are `ccos/plugins/coding/error_recovery/error_recovery.py:45,60,95`. Nothing in `core/agent.py`, `core/task_executor.py`, `core/daemon.py`, `core/inference*.py` or `main.py` calls it. The agent's error handling does not route through the designed fallback-strategy switcher; it is reachable only if an agent explicitly invokes that CCOS capability. 521 lines of complete-looking code with no caller on the hot path. |
| `core/checkpoint.py` | **PARTIAL — one narrow caller** | `create_checkpoint()` `:66` is called from exactly one place: `core/filesystem.py:73`, guarded by `is_core_file()` (self-modification of repo core files). `core/filesystem.py` is reachable via `tools/file_tools.py:12` and `tools/patch_tools.py:96`, which are the agent's real write tools. But `rollback()` `:184`, `list_checkpoints()` `:235`, `get_latest_checkpoint()` `:262`, `prune_checkpoints()` `:269` have **no callers** (same search, minus `./tests/` and the module itself) → checkpoints are created and never listed, pruned, or rolled back from any entry point. Unbounded growth and a write-only safety net. |

---

## (f) DORMANT findings (consolidated)

1. **`config.json` `gui` block (port 8888) has zero consumers** — a stale leftover from the GUI
   removed in `65c9f10` / `63ab3df`. `config.json:11-14`; searched
   `grep -rn "8888\|get_gui_config\|\"gui\"\|'gui'" --include=*.py --include=*.sh .` → nothing.
   The real dashboard is `/admin` on 8770 (`restoricon_core/api/server.py:321`). The GUI-removal
   round's own review notes called for sweeping the `8888` port constants
   (`.claude/agent-memory/code-reviewer/gui_removal_round_changes_requested.md:35-37`);
   `config.json` was the one site missed. **Stale config, not a missing server.**
2. **Aigentik port config is read and discarded.** `a_port` parsed at `service_manager.sh:285,
   436, 496`, never used; and `~/Codey-Aigentik/index.js` binds nothing.
3. **`core/resource_bus.py`'s generic API is dead**: `request_resource` `:446`,
   `release_lease` `:565`, `poll_queue` `:578`, `reap_stale_records` `:295` — zero callers.
4. **`core/recovery.py` is unreachable from the agent/daemon**; only a CCOS plugin wraps it.
5. **`ThermalManager.reset()` has no automatic trigger**; the "cooldown period" its docstring
   names (`core/thermal.py:159`) does not exist as a key in `THERMAL_CONFIG` — verified by
   dumping all nine keys at `utils/config.py:166-178`, not by grepping for `cooldown`. Thread
   reduction is effectively one-way per process. See (d) for both halves of the evidence.
6. **`core/checkpoint.py`'s rollback/list/prune half is unreachable** (see (e)).
7. **No PID file for the embed server.** `core/embed_server.py` writes none (contrast
   `core/loader_v2.py:807-813`); it kills by `os.killpg(os.getpgid(self.process.pid), ...)`
   (`core/embed_server.py:257, 266`) which only works for the process that spawned it. If the
   daemon dies without running its `finally:` `stop_embed_server()` (`core/daemon.py:1345-1347`),
   port 8082 is held by an untracked process. `core/embed_server.py` does have a port-occupant
   /proc scan + kill-and-replace path (`:360, 413, 474, 532, 545, 563`) that partly covers this,
   and `codeydOS`'s `kill_llama_server_gracefully()` (`codeydOS:140-158`) handles **only** port
   8080 — never 8082.
8. **No CCOS process in the service topology.** `start_all_services` (`service_manager.sh:891-899`)
   starts nothing from `ccos/`. CCOS is reachable only as in-process imports:
   `main.py:561` and `restoricon_core/api/routes.py:533`, both
   `from ccos.core.plugin_manager import get_plugin_manager`. The "OS shell" that CLAUDE.md
   describes as discovering/routing/monitoring capabilities has **no standalone runtime** — it is
   a library loaded by two other processes. **This is the largest architectural divergence A1
   found** — a documented top-level layer with no runtime of its own.
9. `setup.sh` / `setup_repo.sh` are orphaned installer scripts not referenced by `install.sh:586-630`.
10. **A dashboard-only user is invisible to the interactivity signal.**
    `is_interactive_session_active()` (`core/resource_gate.py:3961-3981`) now resolves to
    `is_tui_session_active()` alone, which scans `TUI_SESSIONS_DIR` for live per-PID files
    (`core/resource_gate.py:3865`, `utils/config.py:344`). Searched
    `grep -rn "TUI_SESSIONS_DIR\|_write_tui_pid_file" --include=*.py .` → the **only** writer is
    `main.py:401-447`, called at `main.py:2180` around the TUI `repl()`. Nothing in
    `restoricon_core/` writes a session marker. Consequence: someone working entirely through the
    `/admin` dashboard on 8770 registers as "no human present", so every consumer of this signal
    behaves as if the device were idle — the daemon's background-dispatch deferral
    (`core/daemon.py:1288, 1488`), the interactive-vs-background `n_ctx` choice
    (`core/loader_v2.py:1363-1372`, `utils/config.py:150`), and the context-budget admission in
    `core/inference_hybrid.py:430` / `core/plannd.py:875` / `restoricon_core/api/routes.py:3449`.
    `core/resource_gate.py:3977-3980` anticipates exactly this ("if a GUI is ever reintroduced,
    restore the signal WITH a freshness/liveness guard"); the web dashboard *is* that
    reintroduction and the signal was not restored. Given the standing "dashboard = single control
    surface" directive, **this is the behavioural gap most likely to bite a real user** — distinct
    from f8, which is an architectural-divergence finding rather than a misbehaviour.
11. **The model-load path has a second owner outside the daemon.**
    `~/Codey-Aigentik/index.js:228` invokes `tools/ensure_model_cli.py`, whose `main()` calls
    `core.loader_v2.get_loader()` directly (`tools/ensure_model_cli.py:92`) — loading the model in
    a short-lived Node-spawned Python process rather than via the daemon. The release side does go
    through the daemon socket (`tools/release_model_cli.py:73, 77`). Both run with
    `stdio: 'ignore'`, so every failure is silent on the Aigentik side. Not dormant — the opposite:
    reachable from `start_all_services` step 3 and from Aigentik's own mail-polling loop. Flagged
    because (1) it is a concurrent model-load entry point on a ~10.8 GB device (CLAUDE.md rule 2),
    and (2) the load/release asymmetry means a crash of the Node process between `:228` and `:1740`
    leaves the model resident with no owner. The per-port lock
    (`core/loader_v2.py:564-600`) and the resource-gate slot reservation
    (`core/loader_v2.py:1450`) are the mechanisms that make this safe; whether they are sufficient
    under a real concurrent Aigentik+daemon load was not verifiable statically.

---

## (g) TODO / stub inventory

Searched `grep -n "TODO\|FIXME\|XXX\|NotImplementedError\|HACK"` across all A1-scope files
(`core/loader_v2.py core/daemon.py core/inference*.py core/thermal.py core/sysmon.py
core/resource_bus.py core/observability.py core/recovery.py core/checkpoint.py
core/embed_server.py utils/config.py lib/service_manager.sh install.sh main.py
restoricon_core/api/server.py`).

**No `NotImplementedError`, no `FIXME`, no `HACK`, no stub `pass` in any A1-scope file.** Every
`TODO` hit is a *citation of the archived `docs/archive/TODO.md`*, not an open code marker:

- `core/loader_v2.py:168, 174, 312, 1363, 1371, 1417`
- `core/daemon.py:55, 491`
- `core/inference.py:78`
- `core/embed_server.py:191`
- `utils/config.py:59, 116, 124`
- `main.py:160, 1894`

That is itself a maintenance finding: 15 live source comments cite a document CLAUDE.md declares
superseded and "never plan work from" — and `core/loader_v2.py:1417` additionally cites
`CODEY_OS_MASTER_VISION.md`, also archived. Anyone following these pointers lands in `docs/archive/`.

Related dead-flag sites already acknowledged in-source:
- `MODEL_CONFIG["kv_type"]` dead (`utils/config.py:109`; noted `core/resource_gate.py:973-979`).
- `--reverse-prompt` loop deleted as vestigial (`core/loader_v2.py:715-725`, NEW-755).
- `PLANNER_MODEL_PATH` kept identical to `MODEL_PATH` for compatibility only
  (`utils/config.py:471-495`).
- `EMBEDDING_CONFIG["embedding_model"] = "all-MiniLM-L6-v2"` is a stale legacy key; the real
  model is nomic-embed (`utils/config.py:383`, self-documented).

---

## (h) Contradictions between docs and source

1. **CLAUDE.md's repo map is materially out of date.** It lists no `restoricon_core/`,
   `telemetry/`, `codey_estimator/`, or `bench/` — four substantial top-level packages, one of
   which (`restoricon_core/`, 266 KB `routes.py` + 574 KB `web_surfaces.py`) is the single
   largest service in the topology and the only HTTP surface. It also omits `codey` and
   `codey-metrics` from the entry points while naming `codey-start`/`codey-stop` as "the unified
   entry points"; in source, `codey` (`codey:24-73`) is the superset and `codey-start` is a thin
   subset of it.
2. **CLAUDE.md describes CCOS as "the OS shell" that "discovers, routes, monitors"** and says the
   OS shell is governed by `codey-start`/`codey-stop`. In source, `codey-start` starts no CCOS
   process at all (`service_manager.sh:891-899`); CCOS is an in-process import only (finding f8).
3. **`core/resource_bus.py:6` docstring says the coordination DB is at `~/.codey/resource_bus.db`.**
   `_get_db_path()` (`:112-115`) resolves it under the state dir, and the live file is
   `~/.codeyOS/resource_bus.db`. `~/.codey/` does not exist on this device. Docstring path is wrong.
4. **`core/thermal.py:159`** documents a cooldown-triggered reset that has no implementation or
   config key (finding f5).
5. **`config.json` advertises a GUI server on 8888** that does not exist (finding f1). Given the
   standing "dashboard = single control surface" directive, a stale port in the live config file is
   actively misleading about where the control surface is.
6. **`restoricon_core/api/server.py:264-274`** is candid that `stop()` + `start()` is not a
   supported restart (it closes the socket and the DB handle) — but `codey restart`
   (`codey:49-55`) stops and starts all services including this one, relying on full process
   replacement. Not a bug as written, but the docstring's "separate, out-of-scope finding" is
   load-bearing for anyone who tries to make `restart` in-process.
7. `codeydOS:13-20` documents the retirement of the port-8081 `plannd` daemon and the code matches
   (`utils/config.py:471-495`); this one is consistent and is noted as a positive.
8. **`CODEY_MASTER_PLAN.md` / CLAUDE.md still describe `core/voice.py` as present-and-broken and
   list `core/plannd.py`+`planner*.py` as separate planners.** Both files exist, but planning is a
   thinking-mode request against the single port-8080 server (`codeydOS:105-124`,
   `utils/config.py:471-495`). A1 did not audit `voice.py`'s reachability — flagged for whichever
   census task owns it, not asserted here.

---

## (i) Open questions

1. **Does `resource_gate`'s KV-cache cost model account for the hybrid SSM architecture?**
   The GGUF shows `full_attention_interval = 4` with `ssm.*` state parameters, i.e. ~8 of 32
   blocks hold a KV cache and the other 24 hold fixed-size SSM state. A per-layer KV estimate
   over 32 blocks would overestimate by roughly 4×; `MODEL_CONFIG["kv_type"]` being dead means
   the real cache type is the build default, not `q4_0`. This needs a dedicated pass over
   `core/resource_gate.py`'s `ModelSpec` cost math (A1 did not audit those 4911 lines).
2. **Who owns port 8082's lifecycle when the Core API process is the only live consumer?**
   `core/inference.py:101-105` lazily health-checks and may start it; the daemon starts it
   eagerly. If the daemon is down but the Core API is up, the embed server is started by whichever
   process calls `infer()` first and has no PID file. Worth a rule-4 review.
3. **Is `start_all_services`' lack of readiness gating acceptable?** `start_restoricon`
   (`service_manager.sh:247-258`) declares success 0.5 s after fork; the Core API constructs
   ~15 services and a `ThreadingHTTPServer` bind in `__init__` (`restoricon_core/api/server.py:158-238`).
   A bind failure (port in use) would raise *after* the PID file is already written.
4. **Should `core/recovery.py` be wired into the agent loop or deleted?** 521 lines, zero core
   callers. Same question for the generic `resource_bus` API (f3) and
   `checkpoint.rollback/list/prune` (f6).
5. `config.json` holds a live Cloudflare tunnel token in plaintext (`config.json:3`) and the DR
   escrow pubkey (`:9`). The file **is** gitignored (`.gitignore:30`, with
   `!config.json.example` at `:33`) and `git ls-files` confirms it is untracked, so this is not a
   repo leak — noting it only as plaintext-on-device, and `show_service_config` does redact
   token-shaped keys when printing (`service_manager.sh:980-993`).
6. **254 hex-named directories in the repo root are leaked `resource_bus` test state — root cause
   identified.** `ls -d [0-9a-f][0-9a-f][0-9a-f][0-9a-f]* | wc -l` → `254`, dated Sep 3–9. Each
   contains exactly `resource_bus.db` (28,672 bytes) + `resource_bus.lock` (0 bytes) — i.e. the
   two files `core/resource_bus.py:112-118` creates under a caller-supplied `state_dir`. Something
   called `resource_bus` with a `uuid4().hex` state dir resolved relative to the **cwd** rather
   than a tmpdir, 254 times. They are hidden rather than fixed: `.gitignore:46` carries a literal
   32-character `[0-9a-f]`-repeated glob added specifically to mask them, and `git check-ignore -v`
   confirms that rule matches. ~7 MB of working-tree noise and a test-isolation defect.
   This is adjacent to the already-logged "working-tree noise cleanup" round, which fixed
   recombiner/optimizer/sandbox test isolation but evidently not this call path. Out of A1's scope
   to fix (read-only), logged here for `NEW_ISSUES.md` per CLAUDE.md rule 8.
7. `.live_verify_scratch/` contains three scripts importing `core.resource_gate`
   (`subtaskF_case_a.py`, `_b.py`, `_b2.py`). Live-verification leftovers, not entry points.
