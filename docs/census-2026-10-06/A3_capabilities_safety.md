# CENSUS A3 — Tool / Capability Layer, Plugins, Sandbox, Policy, Safety

Read-only static inspection of `/data/data/com.termux/files/home/Codey-OS`, 2026-10-06.
No service started, no model loaded, `~/.codeyOS/restoricon.db` never opened.
Every claim below cites `file:line` from a file actually read or grepped in this pass.
Status vocabulary: IMPLEMENTED / PARTIAL / DORMANT / DOCS-ONLY / MISSING.

**Headline:** there are **three disjoint action surfaces** with three different
safety regimes and **no single chokepoint**. The one real gateway-shaped
mechanism (`TermuxAPI.execute`) covers only one plugin, is permanently
fail-closed with no operator switch, and is bypassable by keyword argument on
its sibling module.

---

## (a) Tool system contract

### Surface 1 — the coding agent's `TOOLS` dict (the only model-facing tool surface)

- Declaration: a plain module-level dict, `core/agent.py:335-352`. 11 tools:
  `read_file`, `write_file`, `patch_file`, `append_file`, `list_dir`, `shell`,
  `search_files`, `note_save`, `note_forget`, `peer_delegate`, `crm_query`.
- There is **no schema, no JSON-schema tool spec, no generated tool manifest**.
  Each entry is a lambda that indexes `args` positionally-by-key, e.g.
  `core/agent.py:337` `lambda args: tool_write_file(args["path"], args["content"])`
  — a missing key raises `KeyError`, caught by `execute_tool`'s outer
  `try/except` (`core/agent.py:667`+) and returned as an `[ERROR] ...` string.
- Wire format is **XML-tagged JSON**, not native function calling. Taught to the
  model in `prompts/system_prompt.py:69-73` ("Opening tag: `<tool>` ... Closing
  tag: `</tool>`") with per-verb mappings at `prompts/system_prompt.py:30-41`
  ("Create"/"Write" → `write_file`, "Run:"/"Execute:" → `shell`, etc.).
- Parsing: `parse_tool_call()`, `core/agent.py:618`. Three tolerance layers:
  1. primary regex `<tool>\s*(\{.*)` → `extract_json` (`core/agent.py:636-639`);
  2. **rogue tags** — `<write_file>{json}</write_file>` etc., via
     `ROGUE_TAG_MAP` (`core/agent.py:355-367`), one entry per tool name;
  3. block-style fallback `<write_file path="...">…raw code…</write_file>`
     (`core/agent.py:651-653`).
  Returns `None` on any failure; never raises (`core/agent.py:655-657`).
- Dispatch: `execute_tool()`, `core/agent.py:667`. Unknown name → string error
  (`core/agent.py:680-681`). On success it also does per-tool display, a
  post-write Python lint pass for `.py` writes (`core/agent.py:736`+), and
  learning/telemetry recording.
- History re-serialization: `_format_tool_for_history`, `core/agent.py:662-664`
  — always normalizes back to canonical `<tool>{json}</tool>`.
- **Status: IMPLEMENTED.** This is the live, exercised path.

### Surface 2 — CCOS capability calls (`plugin_manager.call_capability`)

- `ccos/core/plugin_manager.py:446` `call_capability(cap_name, *args, context=None, **kwargs)`.
  Resolution order: registered in-memory handler → owning plugin's
  `execution_mode` (HTTP POST for `external_process`/`remote_bridge`) →
  in-process module function via `cap.implementation` parsed as `"module:func"`
  (`ccos/core/plugin_manager.py:519-523`).
- **Contract is positional/keyword Python** — `**kwargs` are forwarded verbatim
  to the target function (`ccos/core/plugin_manager.py:543`) or serialized into
  an HTTP JSON body (`ccos/core/plugin_manager.py:495-506`). There is **no
  argument validation against `inputs_schema`** anywhere; `inputs_schema` is
  stored on the `Capability` dataclass (`ccos/core/capability_registry.py:45`)
  and populated from the manifest (`ccos/core/plugin_manager.py:386`) but never
  read for validation. Grep for a validator against `inputs_schema` returns only
  the schema-shape check in `ccos/core/manifest_schema_v2.py`.
- **Status: IMPLEMENTED but unvalidated.**

### Surface 3 — the bridge between 1 and 2: `crm_query`

The *only* place the model-facing tool surface reaches a CCOS capability.

- `tool_crm_query`, `core/agent.py:283-332`. The model supplies a `kind`;
  `_CRM_QUERY_CAPABILITIES` (`core/agent.py:234`+) maps it to one of a fixed
  allowlist of capability names (12 in the `crm_core_query` manifest). Unknown
  kind → error string, never a raw capability name
  (`core/agent.py:308-312`).
- Lazy-loads the `crm_core_query` plugin on the process-global PluginManager
  (`core/agent.py:316-328`), then `pm.call_capability(cap_name, **call_kwargs)`
  (`core/agent.py:330`).
- Kill switch: `CODEY_CRM_TOOL_ENABLED`, default **on**
  (`core/agent.py:269-280`, `core/agent.py:303-304`).
- Manifest permission is `["crm:read"]` (`ccos/plugins/crm/core_query/manifest.json`)
  — read-only by design, and the allowlist is what enforces it, not the
  permission string (see (f)).
- **Status: IMPLEMENTED, narrowly scoped.** This is good design and is the
  template the rest of the system does not follow.

---

## (b) Capability registry analysis

`ccos/core/capability_registry.py` (242 lines) + `ccos/data/capabilities.json`.

### What is registered (parsed directly from the JSON, 2026-10-06)

- **161 capabilities.** Flat dict keyed by dotted name.
- **All 161 have `status: "active"`.** Zero `experimental`, zero `broken`, zero
  `disabled` — even though `CapabilityStatus` defines all four
  (`ccos/core/capability_registry.py:19-23`) and `ToolRouter._score_candidate`
  has an explicit experimental penalty that can therefore never fire
  (`ccos/core/tool_router.py:178-180`).
- **Only 8 of 161 have `use_count > 0`.** 153 have never been invoked.
- By category: coding 46, system 32, device 15, storage 11, speech 7, network 6,
  audio 4, telephony 4, hardware 4, notification 4, general 3, camera 3,
  vision 2, voice 2, security 2, media 2, ui 2, clipboard 2, sensor 2, sms 2,
  and 1 each for research, crm, contacts, location, sharing, automation.
- `ccos/data/capabilities.json` is **gitignored** (per project memory, confirmed
  by its absence from `git status`). It is therefore a **runtime cache written
  by whatever last called `register()`, not a curated, reviewed inventory.**
  `register()` unconditionally overwrites by name and immediately `_save()`s
  (`ccos/core/capability_registry.py:93-97`).

### Orphaned / stale entries — registry is not self-cleaning

- `speech.tts`, `speech.tts_engines`, `speech.stt`, `speech.stt_available` are
  all `status: active` with `implementation` values `tts_speech:speak`,
  `tts_speech:list_engines`, `tts_speech:listen`, `tts_speech:stt_available`.
  **The string `tts_speech` appears in exactly one file in the entire repo:
  `ccos/data/capabilities.json` itself.** There is no `tts_speech` module and no
  `ccos/plugins/speech/<plugin>/` directory — `ccos/plugins/speech/` contains
  only a 0-byte `__init__.py`. These four are **dead registry rows that
  advertise a capability the system cannot perform**, and `call_capability`
  would fall through to `RuntimeError: No loaded plugin implements ...`
  (`ccos/core/plugin_manager.py:555`).
- `test.legacy`, `test.aware`, `test.varkw` are registered `active` — **test
  fixtures leaked into the persisted production registry.**

### Is the registry consulted at runtime, and by whom?

Searched every `.py` in the repo for `get_capability_registry`, excluding
`ccos/tests/`, `tests/`, and `ccos/demo_*`:

| Consumer | Site | Reachable from an entry point? |
|---|---|---|
| `plugin_manager` | `ccos/core/plugin_manager.py:279` | **YES** — 4 production call sites (see (c)) |
| `tool_router` | `ccos/core/tool_router.py:100` | **NO** |
| `agent_orchestrator` | `:192`, `:578` | **NO** |
| `planner` (ccos) | `ccos/core/planner.py:109` | **NO** |
| `lifecycle_manager` | `:106` | **NO** — zero callers anywhere |
| `goal_engine` | `:120` | **NO** |
| `auto_improvement_loop` | `:53` | **NO** |
| `capability_optimizer` | `:79` | **NO** |
| `skill_recombiner` | `:252`, `:512` | **NO** |
| `reflection_engine` | `:58` | **NO** |
| `domain_router` | `ccos/core/domain_router.py:122` | **NO** |

**Decisive reachability evidence.** Grepping `^\s*from ccos|^\s*import ccos`
across `main.py core/ tools/ utils/ restoricon_core/ pipeline/ bench/
telemetry/ codey_estimator/` returns **exactly 9 lines, touching only 2 ccos
modules**:

```
core/agent.py:316            from ccos.core.plugin_manager import get_plugin_manager
core/dashboard_data.py:35    from ccos.core.plugin_manager import get_plugin_manager
core/task_executor.py:355    from ccos.core.plugin_manager import get_plugin_manager
main.py:561                  from ccos.core.plugin_manager import get_plugin_manager
restoricon_core/api/routes.py:533  from ccos.core.plugin_manager import get_plugin_manager
core/peer_cli.py:434,467,487,507   from ccos.core.task_blackboard import get_task_blackboard
```

So: the registry is consulted at runtime **only transitively, via
`PluginManager.__init__`**, and only to `register()` / `unregister()` /
`record_use()` as plugins load and capabilities fire. **No production code
path ever queries it to decide anything** — `query()`, `has()`,
`get_active()`, `find_for_task()`, `get_performance_report()` have no
production callers.

**Status: PARTIAL.** The registry is a write-mostly telemetry sink. The
"AI queries this registry before attempting any task" premise stated in its
own docstring (`ccos/core/capability_registry.py:4-6`) is **DOCS-ONLY.**

### `tool_router.py` — DORMANT

- `get_tool_router()` has exactly two callers: `ccos/core/lifecycle_manager.py:102`
  and `ccos/core/planner.py:110`. Both are themselves unreachable (table above).
  `lifecycle_manager` has **zero callers of any kind** repo-wide.
- Its scoring (`ccos/core/tool_router.py:132-193`) and
  `get_recommendations()` (`:203`) therefore never run in production.
- Module-level `validate_tool_safety()` (`ccos/core/tool_router.py:23`) has one
  non-test caller: `ccos/core/agent_orchestrator.py:1094-1096`, inside
  `execute_plan()` — also unreachable.
- **Status: DORMANT.**

---

## (c) Plugin table — load/work status

### Manifest format

Two generations, both accepted. `ccos/core/plugin_manager.py:313` normalizes
every manifest through `normalize_manifest()` (`ccos/core/manifest_schema_v2.py`).

- **v1 (no `schema_version`)**: `name, version, description, category, author,
  license, entry_point, capabilities[]`. 14 of 20 plugins.
- **v2 (`schema_version: "2.0.0"`)**: adds `domain`, `execution_mode`,
  `permissions[]`, `resource_limits{}`, `process_spec{}`, `dependencies[]`.
  4 plugins: `device_bridge`, `private_agent`, `aigentik`, `crm_core_query`.

Discovery is a fixed two-level scan — `plugins/<category>/<plugin>/manifest.json`
(`ccos/core/plugin_manager.py:300-310`). **Malformed manifests are silently
swallowed** (`ccos/core/plugin_manager.py:331-332`, bare `except Exception: pass`),
so a broken plugin becomes *invisible*, not `BROKEN`.

### The 20 discovered plugins

Checked statically: manifest parses, declared `entry_point` exists on disk,
declared capability count. `load_all()` was deliberately **not** run — it would
spawn the two `external_process` plugins (see below), violating the no-service
constraint.

| # | Plugin | Category | Ver | exec_mode | Caps | Entry exists | Status |
|---|---|---|---|---|---|---|---|
| 1 | `rag_retrieval` | research | 1.0.0 | (v1→in_process) | 1 | yes | loads |
| 2 | `system_info` | system | 1.0.0 | in_process | 2 | yes | loads |
| 3 | `thermal_monitor` | system | 1.0.0 | in_process | 8 | yes | loads |
| 4 | `daemon_control` | system | 1.0.0 | in_process | 7 | yes | loads |
| 5 | `observability` | system | 1.0.0 | in_process | 15 | yes | loads |
| 6 | `camera_capture` | vision | 1.0.0 | in_process | 2 | yes | loads; needs hardware |
| 7 | `device_bridge` | device | 2.0.0 | in_process | 8 | yes | loads |
| 8 | `private_agent` | device | 1.0.0 | **external_process** | 2 | `__init__.py` yes | **see note A** |
| 9 | `termux_api` | device | 1.0.1 | in_process | **41** | yes | loads; 3 caps permanently gated (note B) |
| 10 | `termux_api_extended` | device | 1.0.0 | in_process | 19 | yes | loads; **gate bypassable** (note C) |
| 11 | `static_analysis` | coding | 1.0.0 | in_process | 2 | yes | loads |
| 12 | `agent` | coding | 1.0.0 | in_process | 3 | yes | loads — the primary live capability |
| 13 | `git_integration` | coding | 1.0.0 | in_process | 16 | yes | loads |
| 14 | `finetune` | coding | 1.0.0 | in_process | 9 | yes | loads |
| 15 | `task_queue` | coding | 1.0.0 | in_process | 7 | yes | loads |
| 16 | `error_recovery` | coding | 1.0.0 | in_process | 4 | yes | loads |
| 17 | `peer_escalation` | coding | 1.0.0 | in_process | 5 | yes | loads |
| 18 | `aigentik` | voice | 1.0.0 | **external_process** | 2 | `__init__.py` yes | **see note A** |
| 19 | `crm_core_query` | crm | 1.0.0 | in_process | 12 | yes | loads — the only `TOOLS`-bridged plugin |
| 20 | **`speech/` — NO PLUGIN** | speech | — | — | 0 | n/a | **MISSING** (see below) |

Declared capability total across manifests = 165; registry holds 161 — the gap
is accounted for by the 4 orphan `speech.*` rows plus 3 `test.*` fixtures
displacing real ones by name collision.

**Note A — the two external_process plugins never actually self-host.**
Both `private_agent` (`ccos/plugins/device/private_agent/manifest.json`) and
`aigentik` (`ccos/plugins/voice/aigentik/manifest.json`) declare
`process_spec.start_command` (`["python3","agent.py"]` and
`["python3","-m","aigentik.server"]`) with `working_dir` defaulting to the
plugin dir (`ccos/core/plugin_manager.py:135`). Neither plugin dir contains
`agent.py` or an `aigentik/` package — `ccos/plugins/device/private_agent/`
holds only `manifest.json`, `__init__.py`, and a stale `private_agent.pid`.
Verified by directory listing: `ccos/plugins/device/private_agent/` contains
only `__init__.py` (158 B), `manifest.json`, `private_agent.pid`;
`ccos/plugins/voice/aigentik/` contains only `__init__.py` (147 B),
`manifest.json`, `aigentik.pid`. No `agent.py`, no `aigentik/` package.
`subprocess.Popen` will raise `FileNotFoundError`, caught at
`ccos/core/plugin_manager.py:170-174` → `PluginStatus.BROKEN`. **Both are
registered-but-broken.** Their 4 capabilities (`device.secure_relay`,
`device.local_action`, `voice.stream_dialogue`, `voice.synthesize`) are
nonetheless `status: active` in the registry with `http://127.0.0.1:876{5,6}/...`
implementations.

**`ccos/plugins/speech/` is MISSING as a plugin** — directory exists with only a
0-byte `__init__.py` (`ls -la` confirms), yet 4 `speech.*` capabilities sit
`active` in the registry. This is the exact finding class the census targets.

**`core/voice.py` — verified NOT broken-as-a-module, but orphaned from CCOS.**
The file exists (11,937 bytes, `core/voice.py`), is syntactically a complete
`VoiceManager` wrapping `termux-tts-speak` / `termux-speech-to-text`
(`core/voice.py:9-11`, class at `:27`). It has 3 real importers, all in the
CLI: `main.py:1350`, `main.py:1824`, `main.py:1857`. It is **not** the backing
for the `speech.*` capabilities — those point at the nonexistent `tts_speech`.
So the accurate statement is: `core/voice.py` is **PARTIAL** (code present,
CLI-wired, runtime success depends on the Termux:API app being installed —
`core/voice.py` probes with `shutil.which`), and the *registry's* speech
entries are **broken/orphaned**, which is a different and worse problem than
the doc claim.

### Plugin loading from production — who actually loads what

- `main.py:561-580` — loads only `"agent"`, calls `coding.run_agent`. The CLI's
  unified agent entry.
- `core/task_executor.py:355-399` — loads only `"agent"`, calls
  `coding.run_agent` with `shell_fn=self._daemon_shell`. The daemon path.
- `restoricon_core/api/routes.py:533-537` — loads only `"crm_core_query"`
  (AI Sales Copilot, read-only by design per the comment at `:505-517`).
- `core/agent.py:316-328` — loads only `"crm_core_query"`.
- `core/dashboard_data.py:35-40` — **calls `_plugins.load_all()`**. This is the
  one place that loads *every* plugin, including the two `external_process`
  ones, i.e. **opening the dashboard attempts to spawn external processes**
  (which, per note A, currently just marks them BROKEN — but the intent is a
  spawn, and if the missing entry files are ever added, the dashboard becomes a
  process-spawning trigger). Flag for the safety plan.

### Manifest fields that are validated but never enforced

- `resource_limits.max_memory_mb` / `max_cpu_percent`: schema-checked at
  `ccos/core/manifest_schema_v2.py:80-81, 172`, stored at
  `ccos/core/plugin_manager.py:384`. Repo-wide grep for `setrlimit` / `RLIMIT`
  in non-test code: **zero hits**. The only other `max_memory_mb` is an
  unrelated daemon config default (`core/daemon_config.py:41`). **DORMANT.**
- `process_spec.restart_policy` / `max_restarts`: validated at
  `ccos/core/manifest_schema_v2.py:221-227`. `ProcessSupervisor`
  (`ccos/core/plugin_manager.py:107-258`) contains **no restart logic at all** —
  `start_external_plugin`, `stop_external_plugin`, `check_health`, nothing else.
  **DORMANT.**
- `permissions[]` (plugin and capability level): validated as "a list of
  strings" at `ccos/core/manifest_schema_v2.py:290`. Grep for `.permissions`
  across `ccos/` excluding tests returns **only that one validation line**.
  No runtime check ever consults a plugin's or capability's permissions.
  **DORMANT — the permission strings are decorative.** See (f).

### Credit where due: ProcessSupervisor respects Rule 3

`stop_external_plugin` (`ccos/core/plugin_manager.py:176`) tracks the exact
`Popen` PID or reads it from the PID file, SIGTERMs that PID only, polls, then
escalates to SIGKILL on that PID only (`:229-233`). No name-pattern kill
anywhere. PID files are namespaced under `CODEY_STATE_DIR/plugins/`
(`ccos/core/plugin_manager.py:60`) with a documented rationale for avoiding
collision with `lib/service_manager.sh`'s own supervisor
(`ccos/core/plugin_manager.py:45-58`). **IMPLEMENTED, correct.**

---

## (d) Sandbox — what it isolates and what it does not

`ccos/core/sandbox.py` (342 lines).

### What it does

1. **Substring blocklist.** `BLOCKED_COMMANDS` — 8 literal patterns
   (`rm -rf /`, `rm -rf ~`, `mkfs`, `dd if=`, fork bomb, `chmod 777 /`,
   `chown root`, `> /dev/sda`) matched case-insensitively as substrings
   (`ccos/core/sandbox.py:32-41`, checked at `:85-91`).
2. **cwd allowlist.** `exec_cwd` must resolve inside `ALLOWED_DIRS`
   (`ccos/core/sandbox.py:196-201`).
3. **Path-token scan.** `_find_disallowed_path_token`
   (`ccos/core/sandbox.py:105-163`) shlex-splits the command and rejects
   absolute/`~`/`../` tokens resolving outside the allowlist. Its own docstring
   honestly enumerates what it misses — env expansion, command substitution,
   encoding, relative escape after `cd` — and it **fails open on a shlex
   parse error** (`:155-156`).
4. **Timeout** (`min(timeout, MAX_TIMEOUT=120)`, `:214`) and **output
   truncation** (1 MB, `:219-220`).
5. `install_package` blocks `; && | \`` in a package name
   (`ccos/core/sandbox.py:300-304`).

### What it does NOT isolate

- **Same UID, same process tree, same filesystem.** `subprocess.run(command,
  shell=True, ...)` — `ccos/core/sandbox.py:208-216`. It uses a **real shell**,
  so every metacharacter is live; the only thing standing between the shell and
  the filesystem is the substring blocklist and the token scan.
- **Full environment inheritance.** `exec_env = os.environ.copy()`
  (`ccos/core/sandbox.py:203`). Any secret in the parent env —
  `OPENROUTER_API_KEY`, `UNLIMITEDCLAUDE_API_KEY`,
  `CLOUDFLARE_TUNNEL_TOKEN` (`utils/config.py:451, 463, 666`) — is readable by
  sandboxed code.
- **No namespace, cgroup, seccomp, chroot, or rlimit.** Grep for
  `setrlimit`/`RLIMIT` in non-test code: zero hits. No memory cap, no CPU cap,
  no process-count cap, no network restriction.
- **`ALLOWED_DIRS` includes the entire `ccos/` package directory** —
  `str(Path(__file__).parent.parent)` at `ccos/core/sandbox.py:25`. **Sandboxed
  code is allowed to rewrite the OS layer's own source**, including
  `sandbox.py` itself. Given rule 1's self-improvement mandate (and
  `capability_optimizer`/`skill_recombiner` being the intended sandbox users),
  this is a self-modification hole, not a theoretical one.
- **No audit trail.** `run_command` returns a `SandboxResult`; nothing is
  appended to any ledger.
- **Reachability:** `get_sandbox()` has exactly two callers,
  `ccos/core/capability_optimizer.py:81` and
  `ccos/core/skill_recombiner.py:511` — both unreachable from any entry point
  (table in (b)). **The sandbox is DORMANT.** Nothing in the live system runs
  through it. In particular, the coding agent's `shell` tool does **not** use
  the sandbox.

### "Worlds" / staging-environment concept

Searched, case-insensitive, word-boundary, across all `.py` excluding tests:
`world`, `staging`, `dry_run`, `dryrun`, `simulate`, `shadow_mode`,
`action_gateway`, `actiongateway`. Results:

- `ccos/core/capability_optimizer.py:175, 198-199` — a `staging/` directory for
  **improved source code files** awaiting promotion. This is a code-promotion
  staging area, not an environment in which actions execute against fake data.
- `ccos/core/telemetry_engine.py:394` `compare_sandbox_vs_real()` — compares
  recorded outcomes of sandbox test runs against recorded real executions.
  Closest conceptual relative, but it is **post-hoc analytics**, not a
  switchable execution target, and it lives in a DORMANT module.
- No `dry_run`, no `simulate`, no `shadow`, no world/environment selector
  anywhere.

**Verdict: a "worlds" / staging-environment concept is MISSING.** There is no
way to run a plan against a non-production target. Every real action executes
directly against the live device, the live filesystem, and the live
`~/.codeyOS/restoricon.db`.

---

## (e) Destructive-action chokepoint inventory + Action Gateway verdict

### Verdict: no Action Gateway exists. MISSING.

There is no module through which real-world actions funnel. Instead there are
**three disjoint surfaces**, each with its own ad-hoc guard, and the gap between
them is the safety problem:

| Surface | Entry | Guard | Audited? |
|---|---|---|---|
| 1. `TOOLS` (agent) | `core/agent.py:667` `execute_tool` | per-tool, inline; interactive confirm | no |
| 2. `call_capability` (CCOS) | `ccos/core/plugin_manager.py:446` | **none** | no |
| 3. Restoricon services | `restoricon_core/services/*` | RBAC + `AuditService.log` | yes (mostly) |

Two sub-surfaces *inside* surface 2 do have real, single-chokepoint gates —
`TermuxAPI.execute` (`ccos/plugins/device/termux_api/termux_api.py:124`, E4) and
`DeviceBridgeServer.handle_envelope` (`ccos/core/device_bridge.py:251`, E4c).
They are the right shape and the right instinct. Neither is a system-wide
gateway: each covers exactly one plugin, neither is consulted by surfaces 1 or
3, and neither records an audit entry.

Crucially: **`execute_tool` never calls `validate_tool_safety`.** Its only
caller is `agent_orchestrator.execute_plan` (`ccos/core/agent_orchestrator.py:1094-1096`),
which is unreachable. And **`call_capability` performs no safety check of any
kind** — not the blocklist, not the registry status, not permissions. So the
one safety validator in the codebase guards the one path nothing uses.

### Exhaustive irreversible-action inventory

#### E1 — Arbitrary shell execution

- **`tools/shell_tools.py:193` `shell()`** — the model-callable `shell` tool
  (`core/agent.py:343`). Guards actually enforced:
  - `is_dangerous()` (`tools/shell_tools.py:126`) → warning + confirm. Matches
    18 literal `DANGEROUS_PATTERNS` (`:85-105`) plus a base-command check
    against 9 `DANGEROUS_COMMANDS` (`:26-36`).
  - `AGENT_CONFIG["confirm_shell"]` → confirm (`tools/shell_tools.py:207-208`).
  - Execution is `shlex.split` + `subprocess.run(args, ...)` with **no
    `shell=True`** (`tools/shell_tools.py:219-226`).
  - **CRITICAL — two guards are DORMANT:**
    - `_validate_command()` (`tools/shell_tools.py:162`), which enforces the
      54-entry `ALLOWED_COMMANDS` allowlist (`:38-83`), has **zero callers
      repo-wide**. The allowlist is never consulted.
    - `validate_command_structure()` (`tools/shell_tools.py:108`), which blocks
      the 15 `SHELL_METACHARACTERS` (`:9-24`), is called **only** from
      `tests/security/test_shell_injection.py` (17 call sites). It is not in
      the production path.
    - **Honest assessment:** the absence of `shell=True` is what actually
      neutralizes `;`, `&&`, `|`, backticks and `$()` — they arrive as literal
      argv strings. So this is *not* a live injection vulnerability. But it
      means `shell()`'s real enforced policy is **"anything not matching 18
      substrings, with a y/n prompt"** — a denylist, not the allowlist the file
      reads as implementing, and `tests/security/test_shell_injection.py`
      passes while testing a function production never calls. That gap is the
      finding.
  - `yolo=True` bypasses every confirmation (`tools/shell_tools.py:210`).
    `core/task_executor.py:393` passes `yolo=True`.
- **`core/task_executor.py` `_daemon_shell`** — the daemon's substitute
  `shell_fn`, installed via `AGENT_CONFIG["_shell_fn"]`
  (`core/agent.py:343`, `utils/config.py:162`). This one *is* a real prefix
  allowlist (`_DAEMON_ALLOWED_PREFIXES`, `core/task_executor.py:48`+) that
  deliberately excludes `git commit`/`push`/`reset`
  (`core/task_executor.py:39`). **IMPLEMENTED — and it is the system's only
  genuinely enforced shell allowlist.** Note the asymmetry: the *unattended*
  daemon is better guarded than the *interactive* agent.
- **`ccos/core/sandbox.py:208`** — `subprocess.run(..., shell=True)`. DORMANT.
- **`ccos/plugins/device/private_agent/manifest.json`** — capability
  `device.local_action`, `inputs_schema: {command: string}`, implementation
  `http://127.0.0.1:8766/action`. **An arbitrary-command device relay,
  registered `active`, dispatched by `call_capability` with zero validation.**
  Currently inert only because the backing process cannot start (note A).
  This is the single most dangerous registry row.

#### E2 — File write / overwrite / delete

- `tool_write_file` (`tools/file_tools.py:116`) → `Filesystem.write`. Guards:
  `WRITE_PROTECTED` names always confirm (`tools/file_tools.py:49-62`, enforced
  `:197-201`); shrink guard (<20% of original for source files, `:160-175`);
  Python syntax guard (`:180-193`); binary-extension refusal (`:196` region,
  list at `:21-47`); `confirm_write` for everything else (`:203-207`).
  **PARTIAL — all bypassed by `yolo`/`confirm_write=False`, which
  `core/task_executor.py:392` sets.**
- `tool_patch_file` (`tools/file_tools.py:216`), `tool_append_file` (`:233`) —
  **no confirmation, no protected-name check at all.** `patch_file` and
  `append_file` can modify `.gitignore`, `CLAUDE.md`, `requirements.txt`
  unprompted, which `write_file` cannot.
- **Undo asymmetry — verified.** `core/filesystem.py` contains **exactly one**
  `_snapshot()` call, at `core/filesystem.py:203`, inside `write()` (`:171`).
  `patch()` (`:221`) and `append()` (`:280`) **take no snapshot**, so an
  in-place `patch_file` edit is unrecoverable through `core/filehistory`.
  `core/filesystem.py` also contains **no** `confirm(`/`ask_confirm` call at
  all — every confirmation in the file path lives in `tools/file_tools.py`,
  and only on the `write_file` branch. So the system's least-guarded file tool
  (`patch_file`: no confirm, no protected-name check, no snapshot) is the one
  the system prompt steers the model toward for edits
  (`prompts/system_prompt.py:33`, "Patch:"/"Update"/"Edit" → `patch_file`).
- `allow_self_modification` — `tools/file_tools.py:84-96` rebuilds the
  `Filesystem` with self-modification enabled when
  `AGENT_CONFIG["allow_self_modification"]` is set. The agent editing its own
  source is a config flag away.
- Deletions (non-test, production code):
  `core/checkpoint.py:290` `shutil.rmtree(backup_dir)`;
  `telemetry/rotate.py:387` `shutil.rmtree(source_dir)`;
  `core/backup_secrets.py:184` `shutil.rmtree(work_dir)`;
  `core/backup_documents.py:128` `os.remove(temp_file_path)`;
  `restoricon_core/api/routes.py:2430` `os.remove(file_info['path'])`
  — **an HTTP-reachable file deletion**;
  `core/resource_gate.py:3261, 3949, 3956`; `core/lora_import.py:289, 513`;
  `core/sessions.py:112`; `main.py:476`; `core/peer_shell.py:385, 536`;
  `ccos/plugins/coding/task_queue/task_queue.py:114`;
  `ccos/plugins/coding/error_recovery/error_recovery.py:148`;
  PID/socket unlinks at `core/daemon.py:137, 161, 703, 722`,
  `core/loader_v2.py:940`, `ccos/core/plugin_manager.py:198, 239`.
  **None of these pass through any common guard.**

#### E3 — Git state mutation

- `core/githelper.py:124` — `subprocess.run(["git", "push"], ...)`.
  **The only `git push` in production code.** Reached from `main.py:1007`
  (`/git push` slash command, i.e. human-initiated).
- `core/checkpoint.py:115-180` — automatic `git commit` on checkpoint, staging
  only the triggering file (`:134`).
- `core/checkpoint.py:215-225` — rollback via `git checkout <hash>`.
- Model-reachable: `git` is in `ALLOWED_COMMANDS` (`tools/shell_tools.py:62`)
  but that allowlist is dormant; what matters is that `git` is **not** in
  `DANGEROUS_COMMANDS`, so `shell("git push --force")` gets only the
  `push --force` / `push -f ` / `reset --hard` `DANGEROUS_PATTERNS` hits
  (`tools/shell_tools.py:97-99`) → confirm prompt, bypassed under `yolo`.
  The daemon path excludes git writes properly (`core/task_executor.py:39`).

#### E4 — Device actuation (SMS, calls, camera, torch, wallpaper, wifi, NFC, job scheduler)

`ccos/plugins/device/termux_api/termux_api.py` — 41 capabilities, data-driven
`_TOOL_DATA` table (`:56`+). **This is the one genuinely gateway-shaped
mechanism in the codebase:**

- Single `execute()` chokepoint (`:124`) for all 41.
- Name must be in `TOOL_DEFINITIONS` (`:126-128`) — no arbitrary commands.
- `if spec.dangerous and not self.allow_dangerous: raise` (`:135-136`).
- `shutil.which` availability check (`:137-138`).
- Explicit per-capability argv construction (`_build_args`, `:168`+) with
  `shell=False` (`:147`) — the docstring at `:169-170` states the intent
  plainly: model-controlled values can never become shell syntax.
- `dangerous=True` capabilities: `device.share` (`:75`), **`device.sms_send`**
  (`:77`), **`device.telephony_call`** (`:91`).

**But:** `get_termux_api()` (`:258-262`) constructs `TermuxAPI()` with the
default `allow_dangerous=False`, and grep shows **`allow_dangerous=True` is
passed nowhere outside `ccos/plugins/device/termux_api/test.py:29`.** There is
no env var, no config key, no operator switch. Consequences:
1. **Safety:** SMS send and phone calls are currently unreachable — they always
   raise. Good.
2. **Correctness:** `device.sms_send`, `device.telephony_call`, `device.share`
   are nonetheless `status: active` in the registry, and the `sms`/`telephony`
   categories (4 caps each) are advertised to any registry consumer. **Three
   permanently-failing capabilities registered as active.**
3. **Design gap:** when SMS/calling is eventually needed (it is squarely in the
   Restoricon scope), the only way to enable it is a global flag that unlocks
   *all three* at once. There is no per-capability grant and no approval flow.

**Still-reachable device actions with `dangerous=False`** that are arguably
irreversible or privacy-relevant, and get **no gate whatsoever**:
`device.clipboard_set` (`:65`), `device.notification` (`:71`),
`device.camera_photo` / `device.camera_record` (`:60-61`),
`device.microphone_record`, `device.torch`, `device.wallpaper`,
`device.wifi_enable`, `device.volume`, `device.brightness`,
`device.job_scheduler` (persistent background scheduling —
`termux_api.py:_build_args` handles `--persisted`),
`network.download`, `network.open_url`, `hardware.ir_transmit`.
Reading surfaces with no gate: `device.sms_list`, `device.contact_list`,
`device.location`, `device.clipboard_get`, `call_log`.

#### E4b — `termux_api_extended`: the gate is bypassable by keyword

`ccos/plugins/device/termux_api/extended_api.py` reimplements the gate as a
plain default argument instead of instance state:

```
extended_api.py:15  def _run(command, args=None, input_text=None, dangerous=False, allow_dangerous=False):
extended_api.py:16      if dangerous and not allow_dangerous: raise ExtendedTermuxAPIError(...)
extended_api.py:85  def saf_rm(uri, allow_dangerous=False, **kwargs): return _run("termux-saf-rm", [uri], dangerous=True, allow_dangerous=allow_dangerous)
extended_api.py:54  return _run("termux-keystore", args, dangerous=command=="delete", allow_dangerous=allow_dangerous)
extended_api.py:68  return _run("termux-nfc", args, dangerous=action=="write", allow_dangerous=kwargs.get("allow_dangerous", False))
extended_api.py:89  return _run("termux-notification-channel", args, dangerous=delete, allow_dangerous=kwargs.get("allow_dangerous", False))
```

These are re-exported as capabilities at
`ccos/plugins/device/termux_api/capability_tools.py:50-60`
(`keystore`, `nfc`, `saf_rm`, `notification_channel`, …), and
`call_capability` forwards `**kwargs` verbatim
(`ccos/core/plugin_manager.py:543`). **A defaulted keyword parameter is not a
policy boundary:** any caller that controls the kwargs can pass
`allow_dangerous=True` and the gate yields — for SAF file deletion (`saf_rm`),
**Android keystore key deletion** (`keystore(command="delete")`), NFC tag
write, and notification-channel deletion.

Additionally **`saf_write` is not marked dangerous at all**
(`extended_api.py:84`) — it would overwrite an arbitrary SAF-accessible storage
document with caller-chosen content, outside Termux's own filesystem and
outside every path allowlist in the codebase.

**Status: LATENT defect, not a live bypass — downgraded on reachability
evidence.** To be explicit about what this census does *not* show: no production
`call_capability` site forwards caller- or model-controlled kwargs to an
`extended_api` capability. The five production sites are `main.py:561` and
`core/task_executor.py:355` (both `coding.run_agent`, fixed kwargs),
`core/agent.py:330` (allowlisted to the 12 `_CRM_QUERY_CAPABILITIES` names),
`restoricon_core/api/routes.py:533` (`crm_core_query`), and
`core/dashboard_data.py:37` (`system.monitor_snapshot`). The layer that *would*
pass through arbitrary step kwargs is the orchestrator/planner path, which is
DORMANT (see (h) items 2-4). So this sits in the same bucket as
`device.local_action`: **inert today only because the surrounding layer is
dead, and live the moment that layer is wired** — which is open question #1.
It should be fixed before, not after, CCOS orchestration is enabled.

#### E4c — `ccos/core/device_bridge.py`: the second gateway-shaped mechanism

**Answering task item 8 directly, with a correction to its framing:
`ccos/core/device_manager.py` is NOT an actuation module.** All 515 lines are
read-only hardware *detection* — `_detect_os` (`:35`), `_detect_cpu` (`:86`),
`_detect_ram` (`:122`), `_detect_gpu` (`:149`), `_detect_cameras` (`:188`),
`_detect_audio` (`:212`), `_detect_storage` (`:254`), `_detect_network` (`:287`),
`_detect_connected_devices` (`:321`) — feeding predicates
(`has_camera` `:465`, `has_microphone` `:468`, `is_android` `:480`) and
`get_capabilities_hints()` (`:483`), which `ToolRouter` uses as a hard hardware
filter (`tool_router.py:145-147`). It writes nothing and actuates nothing.
It is also **DORMANT** — `get_device_manager()` callers are `planner.py:111`,
`reflection_engine.py:59`, `tool_router.py:101`, all unreachable.

**Real device actuation lives in two places:** the `termux_api` plugin (E4/E4b)
and `ccos/core/device_bridge.py` (573 lines), which backs the `device_bridge`
plugin (`ccos/plugins/device/bridge/bridge.py:7-9`) and its 8 capabilities with
`permissions: ["device:read","device:write","device:telephony","device:ui"]`.

- **Single chokepoint: `DeviceBridgeServer.handle_envelope()`
  (`device_bridge.py:251`)** — envelope parse, auth, safety veto, handler
  dispatch, in that order. Architecturally this is the closest thing in the
  repo to an Action Gateway, and it is the right shape.
- **Auth:** `if self.auth_token is not None and req.auth_token != self.auth_token`
  (`device_bridge.py:262`). **Fail-open** — a server constructed without a token
  authenticates nothing.
- **Safety veto (`device_bridge.py:270-291`):** for `ACTION_SEND_SMS` /
  `ACTION_MAKE_CALL` it calls `validate_telephony_safety` (`:77`), and for
  `ACTION_THIRD_PARTY_MESSAGE` it inlines an equivalent check. Returns
  `status: "blocked"`.
- **But the veto only blocks emergency numbers.** `validate_telephony_safety`
  (`:77-100`) rejects empty input and anything matching `EMERGENCY_NUMBERS`
  (incl. `+1`-prefixed and ≤4-digit short codes). **Every other number passes.**
  There is no do-not-contact check (despite `PERM_WRITE_DNC` /
  `write:do_not_contact` existing in `auth.py`), no rate limit, no recipient
  allowlist, no confirmation, no actor, and no audit record. The client-side
  capabilities `send_sms_capability` (`bridge.py:32`), `make_call_capability`
  (`:37`), `send_third_party_message` (`device_bridge.py:480`),
  `perform_gesture_capability` (`bridge.py:27`, arbitrary touch injection) and
  `launch_app_capability` (`:42`) are all `status: active` in the registry.
- **Reachability:** the **client** is reachable — `bridge.py` is a loaded
  in-process plugin, and `core/dashboard_data.py:37`'s `load_all()` loads it.
  The **server** is not: `get_default_device_bridge_server()`
  (`device_bridge.py:565`) has no non-test caller, and nothing calls `.start()`
  (`:315`). So today a `send_sms_capability` call reaches
  `DeviceBridgeClient.send_request` (`:391`) and fails to connect.
  **Same latent pattern as E4b: correct-shaped gate, thin policy, inert only
  because its server half is never started.**
- `record_device_interaction_to_core` (`device_bridge.py:517`) suggests an
  intended Core-side persistence path for device actions — worth tracing when
  this limb is activated; not inspected further in this pass.

#### E5 — Outbound network / external side effects

- **Email send — `restoricon_core/services/notification_service.py`.**
  `send_email` (`:13`), `send_calendar_invite` (`:37`),
  `send_calendar_cancellation` (`:46`) all funnel through `_post_request`
  (`:53-64`) → `urllib.request.urlopen` POST to
  `http://127.0.0.1:8081` (Aigentik, `:10`) which then reaches **Gmail**
  (comment, `:21`). **Irreversible, externally visible, and:**
  - grep for `has_permission`/`require_permission` in
    `notification_service.py`: **0 hits** — no RBAC;
  - grep for `build_audit_details` in `notification_service.py`: **0 hits** —
    **no audit record of any email Codey-OS sends.**
  This is the most consequential gap in (g).
- `ccos/core/plugin_manager.py:495-506` — `call_capability` POSTs the full
  payload (args, kwargs, serialized `TaskContext`) to a manifest-supplied
  endpoint. The endpoint comes from `cap.implementation` or
  `process_spec.endpoint`/`health_endpoint`
  (`ccos/core/plugin_manager.py:482-492`). **A manifest edit redirects
  capability traffic — including task context — to any URL.** No host
  allowlist, no scheme restriction beyond `startswith("http")` (`:493`).
- `ccos/core/plugin_manager.py:265-270` — health-check GET to a
  manifest-supplied URL.
- `core/backup_secrets.py:162` — `subprocess.run(["age", "-r", ..., "-o", ...])`
  then upload to GCS bucket `restoricon/secrets_backup/secrets.tar.gz.age`
  (`:41`), bucket from `GCS_BACKUP_BUCKET` (`:80`).
- `core/backup_documents.py:110-115` — per-document age-encrypt + GCS upload to
  `restoricon/documents_backup/<path>.age`.
- `network.download`, `network.open_url`, `network.websearch` capabilities
  (`capability_tools.py:37-39`) — ungated.
- `utils/config.py:666` — Cloudflare tunnel token, i.e. a path to exposing a
  local service publicly.

#### E6 — Database writes (live production data)

- `~/.codeyOS/restoricon.db` via `DEFAULT_DB_PATH` (`restoricon_core/database.py:17`).
- **188 raw SQL write statements** (`grep -roiE "INSERT INTO|UPDATE <tbl> SET|
  DELETE FROM" | wc -l`), split meaningfully: **160 in the service/API/auth
  layer** (the ones that mutate business data at request time) plus **28 in
  `database.py`**, which are schema DDL and table-rebuild migrations, not
  service writes. Per-file *matching-line* counts across 17 modules:
  `database.py` 28 (schema/migrations),
  `auth.py` 20, `crm_service.py` 48, `estimate_service.py` 33,
  `operations_service.py` 15, `scheduling_service.py` 10,
  `business_ops_service.py` 9, `pricing_repo.py` 7,
  `automation_service.py` 6, `pricing_job_service.py` 3,
  `commission_service.py` 2, `financing_service.py` 2, `territory_service.py` 2,
  and 1 each in `audit_service.py`, `communication_service.py`,
  `finance_service.py`, `assessment_service.py`.
- Connection acquisition **is** centralized: `DatabaseManager.get_connection()`
  (`restoricon_core/database.py:2444`), WAL + `foreign_keys=ON`
  (`:2456-2459`). That is a *connection* chokepoint, not an *authorization*
  chokepoint — authorization is per-method (see (f)).
- Destructive schema surgery with FKs disabled:
  `restoricon_core/database.py:2986` and `:3143` and `:3337`
  `PRAGMA foreign_keys = OFF;` inside table-rebuild migrations, each followed
  by a `foreign_key_check` (`:3018, 3185, 3390`). Runs automatically from
  `_migrate_schema()` (`:2513`) on `DatabaseManager.__init__` when
  `init_schema=True` (default, `:2418`). **Every process that constructs a
  `DatabaseManager` can rewrite production tables on startup.**
- `restoricon_core/api/expiry_sweep.py` — `EstimateExpirySweepThread`, a
  background thread started by the API server (`server.py:30`) that mutates
  estimate state on a timer.

#### E7 — Process lifecycle

- `ccos/core/plugin_manager.py:224, 232` — `os.kill(pid, SIGTERM/SIGKILL)` on a
  tracked PID (Rule 3 compliant).
- **Verified `_DAEMON_ALLOWED_PREFIXES` in full** (`core/task_executor.py:48-64`):
  `pytest, ls, cat, echo, grep, find, git status, git log, git diff, git show,
  "cd ", pwd, which, env, printenv`. Git writes are genuinely excluded — the
  comment at `:39` is accurate. Python/pip arrive via a separate, narrower
  `_PYTHON_ALLOWED_PATTERNS` (`:70-76`: `"python "`, `"python3 "`,
  `"pip install "`, `"pip3 install "`, `"pytest "`) with `_DANGEROUS_FLAGS`
  `["-c","-e","-exec","--eval","-r","-m"]` blocked (`:68`). This is the
  system's only real, enforced command allowlist.
- `core/daemon.py`, `core/loader_v2.py:940`, `lib/service_manager.sh` — out of
  A3 scope; flagged for the A-series owner of process lifecycle.
- `device.job_scheduler` capability — schedules a **persisted** Android job
  running an arbitrary script path. Ungated (`dangerous=False`).

---

## (f) Policy / RBAC / entitlement state

**Two unconnected policy systems.** One is excellent; the other is decorative.

### System A — Restoricon RBAC: IMPLEMENTED, substantial

`restoricon_core/auth.py` (1,723 lines).

- **10 roles** declared `auth.py:27-39`: `admin`, `manager`, `sales`,
  `sales_manager`, `project_manager`, `technician`, `ai_agent`, `customer`,
  `subcontractor` (+ the set `ALL_ROLES` at `:41`).
- **~90+ fine-grained permission constants**, `auth.py:76-283`+, in
  `verb:resource` form — `read:all_customers`, `write:customers`,
  `read:own_customer`, `sign:contracts`, `read:audit_log`, `manage:users`,
  `write:do_not_contact`, `reassign:any_project_staff`, … including explicit
  own-vs-all-vs-assigned scope tiers.
- `ROLE_PERMISSIONS: Dict[str, Set[str]]` at `auth.py:349`, with derived rather
  than duplicated sets (`auth.py:788` `ROLE_PERMISSIONS[ROLE_SALES_MANAGER] =
  ROLE_PERMISSIONS[ROLE_SALES] | {...}` — good, avoids drift).
- `AuthContext` (`auth.py:999`) carries `user_id`, `role`, `actor_type`;
  `has_permission()` at `auth.py:1012-1016`.
- Credentials: PBKDF2, `SALT_BYTES=16`, `HASH_ITERATIONS=100_000`
  (`auth.py:22-23`); tokens expire in 7 days (`:24`).
- **Enforcement is dense and real: 345 `require_permission` / `has_permission`
  occurrences** (`grep -roE | wc -l`, per-occurrence not per-line) across
  `restoricon_core/services/*.py` + `restoricon_core/api/*.py`. Per-file
  *matching-line* counts, which is what the breakdown below reports —
  `crm_service.py` 135, `operations_service.py` 43, `estimate_service.py` 29,
  `scheduling_service.py` 24, `business_ops_service.py` 18,
  `automation_service.py` 11, `finance_service.py` 9, `analytics_search` 6,
  `commission_service.py` 5, `communication_service.py` 4,
  `financing_service.py` 4, `territory_service.py` 4,
  `assessment_service.py` 3, `audit_service.py` 1, plus
  `api/routes.py` 19. `PermissionError` raised throughout `auth.py`
  (`:1090, 1275, 1339, 1378, 1521, 1574, 1645, 1692`).
- **Entitlement** (distinct from scope) is implemented and the distinction is
  explicitly reasoned about: `restoricon_core/api/routes.py:541-560` documents
  per-panel entitlement derived from the real service method each CCOS
  capability proxies to, and explicitly refuses to let the scope-widening
  `PERM_READ_TEAM_SALES_DATA` double as an entitlement check.
  Confirms the memory note. **IMPLEMENTED.**
- **Gaps:** `notification_service.py` and `pdf_service.py` have **0**
  permission checks. `notification_service` is the email-send path (E5).
  `pricing_repo.py` (7 SQL writes) also has 0.

### System B — CCOS capability permissions: DORMANT / decorative

- Manifests declare `permissions` — `device_bridge`:
  `["device:read","device:write","device:telephony","device:ui"]`;
  `private_agent`: `["device:control","fs:private"]`;
  `aigentik`: `["audio:record","audio:playback","network:local"]`;
  `crm_core_query`: `["crm:read"]`.
- Carried into `Capability.permissions` (`ccos/core/capability_registry.py:44`,
  populated `ccos/core/plugin_manager.py:387`) and `Plugin.permissions`
  (`ccos/core/plugin_manager.py:91`).
- **Never checked.** Grep `.permissions` across `ccos/` excluding tests yields
  one line: the schema-shape validation at
  `ccos/core/manifest_schema_v2.py:290`. There is no permission-granting
  subject, no grant store, no check in `call_capability`.
- **The two systems do not connect.** `AuthContext` is never passed into
  `call_capability`; `TaskContext` (`ccos/core/task_context.py`) carries
  `task_id`/`step_id`/`goal`, not an actor. So a CCOS capability has no notion
  of *who* is invoking it. The `crm_core_query` plugin's read-only safety rests
  entirely on `core/agent.py`'s hardcoded `_CRM_QUERY_CAPABILITIES` allowlist,
  **not** on its `crm:read` permission string.

### System C — the "Safety agent": DORMANT

`agent_orchestrator.py` implements a 5-agent deliberation with a safety
validator — `self._safety.validate_safety(plan)` (`:1070`), `SafetyVetoError`
(`:1081`), and the raw-step path calling `validate_tool_safety` (`:1094-1096`).
`execute_plan` has no caller outside `ccos/` (reachability table, (b)).
**The safety veto has never run in production.**

---

## (g) Secrets & audit logging verification

### Secrets: no keystore, no vault — environment variables + plaintext files

- All runtime secrets come from `os.environ`:
  `utils/config.py:451` `OPENROUTER_API_KEY`;
  `:463` `UNLIMITEDCLAUDE_API_KEY`;
  `:666` `CLOUDFLARE_TUNNEL_TOKEN` / `CLOUDFLARED_TOKEN`;
  `core/backup_secrets.py:80` `GCS_BACKUP_BUCKET`.
  All default to `""` on absence — **fail-open to "no key", not an error.**
- **No `.env` file exists** (`ls .env` → No such file). No dotenv loader in
  `utils/`, `core/`, or `restoricon_core/`. So secrets must be exported by the
  shell — meaning they are in the parent env of every subprocess, including
  `ccos/core/sandbox.py:203`'s `os.environ.copy()`.
- `config.json` (612 bytes, repo root, `0600`) holds non-secret config only:
  keys are `['aigentik','cloudflare','gcs_backup_bucket','gui','restoricon']`.
  A `config.json.example` is committed alongside.
- **Plaintext credential on disk: `~/.codeyOS/gcp_credentials.json`** —
  referenced at `core/backup_documents.py:61` and
  `core/backup_secrets.py:130, 144`. No encryption at rest.
- **Android keystore is NOT used for secrets.** `termux-keystore` is exposed as
  a *capability* (`extended_api.py:38-54`) — and its `delete` branch is the
  bypassable-gate hole from E4b — but nothing in Codey-OS stores or retrieves
  its own secrets there.

### Escrow / DR key: IMPLEMENTED, pending operator action

- `core/setup_dr_key.py` — one-time DR key escrow (`:1`), `_generate_keypair`
  (`:29`), `_print_handoff(private_key)` (`:66`), `main()` (`:92`) with a
  `--force` flag per its argparse description (`:94`).
- `core/backup_secrets.py` — age-encrypts a tar to **two** recipients, the
  at-rest key and the DR key (`:5`, `:163`
  `["age","-r",at_rest_pubkey,"-r",dr_pubkey,"-o",enc_path,tar_path]`),
  uploads to `restoricon/secrets_backup/secrets.tar.gz.age` (`:41`).
  `os.chmod(tar_path, 0o600)` with an explicit "don't trust umask" comment
  (`:158`). Unconditional cleanup of both plaintext and ciphertext (`:178-188`).
  Pubkey format validated by regex `^age1[a-z0-9]+$` (`:39`, `:71`, `:114`).
  **Well built.** The memory note's pending `setup_dr_key.py --force` is still
  outstanding — nothing in this pass changes that.

### Audit logging: IMPLEMENTED in Restoricon, MISSING everywhere else

- Canonical envelope: `build_audit_details(...)` (`restoricon_core/services/audit_service.py:218`)
  + `AuditService.log(action, entity_type, entity_id, change_summary, actor,
  details)` (`:289`). Writes `INSERT INTO audit_log (timestamp, actor_id,
  actor_role, actor_type, action, entity_type, entity_id, change_summary,
  details_json)` (`:310-331`) inside `with conn:` — **transactional with the
  caller's connection**. `actor` defaults to `role="system", actor_type="agent"`
  when absent (`:302-304`). Docstring states append-only, no update/delete path
  through the service (`:298-299`); `query_logs` at `:344` is the only read.
- **Verified live count — the envelope IS applied, and more widely than the
  memory note records.** `build_audit_details` call sites by file:
  `crm_service.py` 63, `estimate_service.py` 23, `operations_service.py` 14,
  `business_ops_service.py` 11, `scheduling_service.py` 11,
  `api/routes.py` 10, `automation_service.py` 6, `commission_service.py` 3,
  `financing_service.py` 3, `territory_service.py` 3,
  `assessment_service.py` 2, `finance_service.py` 2,
  `audit_service.py` 3 (own definition + helpers) — **154 total**.
  Counting `.log(` lines mentioning audit: **137 sites.**
  Sample verified by eye: `crm_service.py:302-308`
  `self.audit.log(... details=build_audit_details(after=customer.to_dict()))`.
  Wiring: `crm_service.py:180, 187` take and store an `AuditService`, and pass
  the same instance to sub-services (`:200, 201, 209`) — one shared audit
  writer, not per-service copies.
  **Correcting the record (rule 6):** project memory records "all 55 service
  audit sites canonical (2026-09-03)". The real figure today is ~137 `.log(`
  sites / 154 `build_audit_details` uses. The 55 was a point-in-time count that
  has since roughly tripled; it should not be cited as current coverage.
- **Services with ZERO audit coverage:** `notification_service.py` (**sends
  email** — E5), `communication_service.py` (0 `build_audit_details`, though it
  has 1 SQL write and 4 permission checks), `pdf_service.py`,
  `pricing_job_service.py`, `pricing_repo.py` (7 SQL writes),
  `analytics_search_service.py` (read-only, acceptable).
- **Nothing outside `restoricon_core/` is audited at all.** No audit record for:
  any `TOOLS` invocation, any `shell` execution, any file write/patch/delete,
  any `git push`, any sandbox run, any device actuation, any
  `call_capability`. `execute_tool` records to a *learning/telemetry* store
  (`core/agent.py:783` `"tool": name`), which is performance data, not an
  append-only accountability ledger.

### `tests/security/`

`tests/security/test_shell_injection.py` — 17 assertions, all against
`validate_command_structure`, which production never calls (E1). The suite is
green and tests a dormant function. This is precisely the
"a fix that passes every test can still be wrong" pattern CLAUDE.md warns about.

---

## (h) DORMANT findings (consolidated)

Each entry states what was searched.

1. **`ccos/core/sandbox.py` — entire module DORMANT.** `get_sandbox()` callers:
   `capability_optimizer.py:81`, `skill_recombiner.py:511`; both modules
   unreachable from any entry point (`from ccos` grep, (b)).
2. **`ccos/core/tool_router.py` — DORMANT.** `get_tool_router()` callers:
   `lifecycle_manager.py:102`, `planner.py:110`; both unreachable.
3. **`validate_tool_safety` — DORMANT.** Non-test caller:
   `agent_orchestrator.py:1094` only, inside unreachable `execute_plan`.
4. **`ccos/core/agent_orchestrator.py` (1,193 lines) — DORMANT.**
   `get_agent_orchestrator()` non-test callers: `ccos/core/planner.py:323` only.
   Nothing outside `ccos/` imports it. Includes the entire 5-agent
   deliberation and the safety veto.
5. **`ccos/core/lifecycle_manager.py` (279 lines) — DORMANT, zero callers.**
   Grep `lifecycle_manager|get_lifecycle` outside the file itself and tests:
   **no matches at all.**
6a. **`ccos/core/device_manager.py` — DORMANT and read-only.** Detection, not
   actuation (see E4c). `get_device_manager()` callers: `planner.py:111`,
   `reflection_engine.py:59`, `tool_router.py:101` — all unreachable.
6b. **`ccos/core/device_bridge.py` `DeviceBridgeServer` — DORMANT server half.**
   `get_default_device_bridge_server()` (`:565`) has no non-test caller; nothing
   calls `.start()` (`:315`). The client half IS reachable via the loaded
   `device_bridge` plugin, so its 8 capabilities are `active` but
   connection-refused.
6c. **`ccos/core/planner.py`, `telemetry_engine.py`,
   `reflection_engine.py`, `domain_router.py`, `performance_tracker.py`,
   `project_engine.py`, `goal_engine.py`, `auto_improvement_loop.py`,
   `capability_optimizer.py`, `skill_recombiner.py` — DORMANT** from
   production entry points, by the same `from ccos` import census. (The
   self-improvement four are expected to be gated per rule 1; the rest are not.)
7. **`tools/shell_tools.py:162` `_validate_command` + the 54-entry
   `ALLOWED_COMMANDS` (`:38-83`) — DORMANT, zero callers repo-wide.**
8. **`tools/shell_tools.py:108` `validate_command_structure` + the 15-entry
   `SHELL_METACHARACTERS` (`:9-24`) — DORMANT in production**, 17 callers all
   in `tests/security/test_shell_injection.py`.
9. **`tools/shell_tools.py:154` `_parse_command` — dead code, zero callers.**
10. **Manifest `resource_limits` (memory/CPU) — DORMANT.** Validated
    (`manifest_schema_v2.py:80-81, 172`), stored
    (`plugin_manager.py:384`), never enforced; no `setrlimit`/`RLIMIT` in
    non-test code.
11. **Manifest `process_spec.restart_policy` / `max_restarts` — DORMANT.**
    Validated (`manifest_schema_v2.py:221-227`); `ProcessSupervisor` has no
    restart code path.
12. **Manifest/capability `permissions` — DORMANT.** Only reference outside
    tests is the shape check at `manifest_schema_v2.py:290`.
13. **`Capability.inputs_schema` / `outputs_schema` — DORMANT.** Populated
    (`plugin_manager.py:386-387`), never used to validate a call.
14. **`CapabilityStatus.EXPERIMENTAL/BROKEN/DISABLED` — DORMANT.** All 161
    rows are `active`; the experimental penalty at `tool_router.py:178` can
    never fire.
15. **Registry query API — DORMANT.** `query()`, `has()`, `get_active()`,
    `get_by_category()`, `find_for_task()`, `get_performance_report()`
    (`capability_registry.py:113-196`) have no production callers.
16. **`ccos/plugins/speech/` — MISSING plugin**, 4 orphan `active` capabilities.
17. **`private_agent` / `aigentik` — registered but cannot start** (missing
    `agent.py` / `aigentik/` under their plugin dirs); 4 `active` capabilities
    pointing at endpoints that will not exist.
18. **`device.sms_send`, `device.telephony_call`, `device.share` — permanently
    fail-closed**, no operator path to enable (`allow_dangerous=True` passed
    nowhere but `test.py:29`).

---

## (i) TODO / stub / artifact inventory

1. **254 orphan hex-named directories at the repo root**, each containing
   `resource_bus.db` (28 KB) + an empty `resource_bus.lock`; e.g.
   `0035ffa098e24b2fb18357972b7c9b75/`, timestamped Sep 3 14:46. Gitignored by
   a 32-char-hex glob at `.gitignore:46` (confirmed via `git check-ignore -v`).
   Test-isolation artifacts from `core/resource_gate.py` that were never cleaned
   up. Not a safety issue; it makes the repo root unreadable and `ls` unusable.
2. **`test.legacy` / `test.aware` / `test.varkw`** — test fixtures persisted as
   `active` capabilities in `ccos/data/capabilities.json`.
3. **Stale PID file** `ccos/plugins/device/private_agent/private_agent.pid`
   committed inside the plugin source dir, which is exactly the anti-pattern
   `plugin_manager.py:45-58` documents moving away from.
4. **`CODEY_OS_MASTER_BLUEPRINT.md` and `docs/directives/` are untracked**
   (`git status`), i.e. the census's own target artifact is not committed.
5. **`restoricon_core/`, `bench/`, `telemetry/`, `codey_estimator/`,
   `lib/`, `setup.sh`, `setup_repo.sh`, `codey`, `codey-metrics`,
   `AGI_AUDIT_PLAN.md`, `ANTIGRAVITY.md`, `sales_rep_portal.md` are absent
   from CLAUDE.md's "Current repo structure" map.** `restoricon_core/` in
   particular is ~4,500 lines of `routes.py` plus 18 services and holds the
   majority of the system's destructive surface and all of its RBAC. A census
   working from the map alone would miss it entirely. Worth a `NEW-###`.
6. `restoricon_core/backfill_wo_351695937.py` and `migrate_aigentik.py` —
   one-off migration scripts living in the package root, both with DB write
   access, both importable.
7. `restoricon_core/database.py:2516-2520` — explicit in-code note that the
   project has **no schema-versioning mechanism**; migrations are idempotent
   `PRAGMA table_info()` checks. Acknowledged debt, not a stub.

---

## (j) Open questions

1. **Is the DORMANT CCOS orchestration layer intended to be wired up, or is it
   superseded?** ~8,000 lines across `agent_orchestrator`, `planner`,
   `tool_router`, `sandbox`, `lifecycle_manager`, `domain_router`,
   `telemetry_engine`, `reflection_engine` have no production caller.
   `core/planner_v2.py` independently provides a `get_planner()` used by
   `core/daemon.py:889` and `core/observability.py:79, 92` — **so there are two
   planners and production uses the `core/` one.** Which is canonical matters
   before any Action Gateway is built, because the natural place for a gateway
   is exactly in the layer that is currently dead.
2. **Should an Action Gateway wrap `TOOLS`, `call_capability`, or both?** They
   are architecturally disjoint today; the `crm_query` allowlist
   (`core/agent.py:234`+) is the only bridge and is the best existing model.
3. **How should `allow_dangerous` be granted?** It currently has no operator
   path at all, and `extended_api.py`'s kwargs form is bypassable. A
   per-capability grant store keyed to an `AuthContext` would unify with
   System A; a global flag will not.
4. **Should `AuthContext` flow into `TaskContext`?** Without an actor, CCOS
   capabilities cannot be RBAC-checked, cannot be audited with an actor, and the
   `permissions` strings cannot ever be enforced. This is the single change that
   would let Systems A and B merge.
5. **Should the dormant `ALLOWED_COMMANDS` allowlist be activated for the
   interactive `shell` tool,** bringing it to parity with the daemon's
   `_DAEMON_ALLOWED_PREFIXES`? Today the unattended path is strictly safer than
   the attended one, which is backwards. Note: `tests/security/` must be
   repointed at the production function in the same change, or it keeps testing
   nothing.
6. **Does an audit record belong on tool/capability invocation?** The only
   append-only ledger is `audit_log`, scoped to Restoricon entities. Nothing
   records that the agent ran a shell command, wrote a file, or sent an email.
7. **`notification_service` email sends: add RBAC + audit?** It is the clearest
   externally-visible irreversible action in the system and currently has
   neither.
8. **`ALLOWED_DIRS` including `ccos/` itself** (`sandbox.py:25`) — intentional
   for the self-improvement path, or an oversight? Under rule 1 this needs an
   explicit decision, not a default.
9. **Are `private_agent` and `aigentik` meant to live in the sibling repos**
   (`~/Codey-Aigentik`, `~/restoricon` are additional working directories)
   with the manifest `working_dir` pointed there? That would make them start —
   which is a safety event, not just a fix, given `device.local_action`'s
   `{command: string}` schema.
10. **Should the `device_bridge` telephony veto be widened before that limb is
    activated?** It blocks emergency numbers and nothing else
    (`device_bridge.py:77-100`). `PERM_WRITE_DNC` / `write:do_not_contact`
    already exists in `auth.py`, and a `do_not_contact` table is implied by it —
    but the veto never consults it. Also: should `handle_envelope`'s auth
    fail *closed* rather than skipping on a `None` token
    (`device_bridge.py:262`)?
11. **Should `ccos/data/capabilities.json` be committed and reviewed?** As a
    gitignored runtime cache it has accumulated 3 test fixtures and 4 orphan
    rows, and no review gate exists for what becomes an `active` capability.

### Deliberately NOT inspected in this pass (so the next reader knows)

- `ccos/core/device_bridge.py:517` `record_device_interaction_to_core` — the
  Core-side persistence hook for device actions. Named, not traced.
- `restoricon_core/api/routes.py` (4,493 lines) — read only around the plugin
  bridge (`:505-560`) and the file deletion (`:2430`). Its full endpoint
  inventory and per-endpoint auth wiring is an A-series task of its own.
- `restoricon_core/api/rate_limiter.py`, `expiry_sweep.py`,
  `web_surfaces.py` — identified, not read.
- `ccos/core/manifest_schema_v2.py` — read for validation coverage only, not
  audited for schema correctness.
- `codey_estimator/`, `bench/`, `telemetry/`, `pipeline/` — out of A3 scope.
- `load_all()` was never executed and no plugin was imported; plugin
  load/work status in (c) is static (manifest parse + entry-point existence),
  **not** a live load test. Rule 7 applies: this is code-level verification,
  not live verification.
