# Codey-OS Self-Measurement / Telemetry Layer — Design (Phase 2)

**Status:** design only. No code written. Requires Ish's approval before
Phase 3 implementation begins.
**Date:** 2026-09-03
**Builds on:** `PROJECT_LOG.md` → "2026-09-03 — Telemetry layer Phase 1
(inventory) complete".
**Purpose of the data:** evidence for an NSF SBIR Phase I application.
Provenance over convenience; append-only and immutable; honest nulls.

Every factual claim in this document about an existing artifact was
verified by reading that artifact during this design pass. Where a claim
in the Phase 1 brief did not survive re-reading, it is corrected inline
and called out in §8.

**Map to the requested deliverable structure:**

| Requested item | Section |
|---|---|
| 1. Reused/wrapped vs. built new (incl. the two conflicts) | §1 (conflicts: §1.3, §1.4) |
| 2. Full schema, all categories + envelope | §2 |
| 3. Every file created or modified | §4 |
| 4. Overhead estimate + measurement procedure | §5 |
| 5. Rotation/retention with bytes/day math | §6 |
| 6. Phase 3 sub-tasks ordered by risk (+ where F sits) | §7 |
| 7. Ambiguous points for Ish's decision | §8 |
| — Storage layout, JSONL-vs-SQLite, cross-language schema, CLI | §3 |
| — Verified-facts table this design rests on | §0 |
| — Plain-language summary | §9 |

---

## 0. Verified facts this design rests on

These were read directly (CLAUDE.md rule 12), not assumed. They are
listed up front because several of them change the design materially.

| # | Fact | Where verified |
|---|---|---|
| 0.1 | `/proc/stat` is permission-denied on this device right now. `head -1 /proc/stat` → `Permission denied`. CPU% is structurally unmeasurable (NEW-108 still live). | live shell, 2026-09-03 |
| 0.2 | **`/proc/uptime` is ALSO permission-denied.** `cat /proc/uptime` → `Permission denied`. Device uptime is not readable. This is a sibling restriction to NEW-108 and is not documented anywhere. | live shell, 2026-09-03 |
| 0.3 | `/proc/sys/kernel/random/boot_id` **is** readable → `85304233-7aa7-40ea-ba9b-7e36c4dd5fa0`. A boot-scoped grouping key is available for free. | live shell, 2026-09-03 |
| 0.4 | llama.cpp's `result_timings` struct has exactly nine fields: `cache_n`, `prompt_n`, `prompt_ms`, `prompt_per_token_ms`, `prompt_per_second`, `predicted_n`, `predicted_ms`, `predicted_per_token_ms`, `predicted_per_second` (+ `draft_n`/`draft_n_accepted` only when speculative decoding is on). | `~/llama.cpp/tools/server/server-task.h:262-280`, `server-task.cpp:240-261` |
| 0.5 | `timings.cache_n` is assigned from `n_prompt_tokens_cache` — i.e. **the prefix-cache hit is already reported by the server, in tokens, per request.** No inference or heuristic needed for category A's "prefix cache hit". | `~/llama.cpp/tools/server/server-context.cpp:501` |
| 0.6 | The non-streaming OAI chat response carries `usage.prompt_tokens_details.cached_tokens`, `usage.prompt_tokens`, `usage.completion_tokens`, `choices[0].finish_reason`, `id` (a server-generated per-request id), and `system_fingerprint` (= `llama_build_info()`). | `server-task.cpp:389-395, 437-482` |
| 0.7 | In **streaming** mode `usage` is emitted **only** when `stream_options.include_usage` is set, but `timings` is appended to the final delta unconditionally when `prompt_n >= 0`. Since `timings` already carries `prompt_n` and `cache_n`, streaming needs **no request-payload change** to get full category-A coverage. | `server-task.cpp:526-541` |
| 0.8 | `core/inference_hybrid.py` currently reads only `predicted_n`/`predicted_ms` out of `timings` and discards `prompt_*`, `cache_n`, `finish_reason`, `id`, and `usage`. The prefill numbers exist on the wire today and are thrown away. | `core/inference_hybrid.py:184-197, 277-293` |
| 0.9 | `core/loader_v2.py` opens `~/.codeyOS/llama-server.log` with mode `"w"` at every server start, truncating it. | `core/loader_v2.py:731-735` |
| 0.10 | **The GUI half of `is_interactive_session_active()` was removed on 2026-09-02.** It now delegates unconditionally to `is_tui_session_active()`. There is no GUI detector to record. | `core/resource_gate.py:3737-3757` |
| 0.11 | **There is no preemption mechanism anywhere in the dispatch path.** `_check_dispatch_gate()` is a *pre-claim* check: a refused task is simply not claimed and stays `pending`. In-flight work is never suspended. | `core/daemon.py:1243-1251, 1294-1302` |
| 0.12 | The daemon main loop ticks at `asyncio.sleep(0.5)`; `_process_planner_tasks()` (and therefore `_check_dispatch_gate()`) runs on every tick while a task is pending. Watchdog work runs every 60 ticks ≈ 30 s. | `core/daemon.py:990, 995-998, 1090` |
| 0.13 | `reserve_context_budget()` executes inside a cross-process `flock` (`_LockedState`). `wait_and_reserve_context_budget()` re-calls it every `CONTEXT_QUEUE_POLL_INTERVAL_SECONDS = 2.0` s until admitted or timed out. | `core/resource_gate.py:3942, 4412-4523` |
| 0.14 | Aigentik's `pruneOldLogs()` only `unlink`s files inside `config.paths.logs_dir` whose names satisfy `startsWith('aigentik-') && endsWith('.log')`. It cannot reach a differently-named file in a different directory. | `~/Codey-Aigentik/logger.js:28-44` |
| 0.15 | Aigentik's `logger.js` writes with `fs.appendFileSync` — a **blocking** call on its single event-loop thread. The new layer must not copy that pattern. | `~/Codey-Aigentik/logger.js:24` |
| 0.16 | `isAddressGrounded()` has four distinct behavioural outcomes, but only one is logged. See §2.F. | `~/Codey-Aigentik/llama.js:536-541, 554-556, 726-728` |
| 0.17 | `chat()` in `llama.js` is a genuine single choke point for every LLM call in Aigentik (local, Gemini, Vertex all route through it). | `~/Codey-Aigentik/llama.js:152-157` |
| 0.18 | `restoricon_core/api/routes.py`'s `/api/v1/ai/chat` proxy returns `resp_data` **verbatim** from llama-server — so `timings`/`usage` already reach this Python code path for every Aigentik local-model call that goes through Core. | `restoricon_core/api/routes.py:1213-1216` |
| 0.19 | `ThermalManager._total_inference_sec` is process-local and resets to 0 on every daemon restart. | `core/thermal.py:61-95` |
| 0.20 | `get_performance_tracker()` is a process-wide singleton over `ccos/data/ccos_memory.db`; its `cap_metrics` table is read by `capability_optimizer`, `goal_engine`, `skill_recombiner`, `auto_improvement_loop` — all four rule-1-gated. | `ccos/core/performance_tracker.py:19-70` + caller grep |
| 0.21 | Live env contains `OPENROUTER_API_KEY`, `UNLIMITEDCLAUDE_API_KEY`, `CLOUDFLARE_TUNNEL_TOKEN`; `~/Codey-Aigentik/config.json` contains `core_api.token`. A naive "dump env / dump active config" for category G would write live secrets into a permanent, exportable, grant-bound store. | `utils/config.py:438-651`, `~/Codey-Aigentik/config.json:59-62` |
| 0.22 | Device: `SM-S928U`, Android `16`, kernel `6.1.145-android14-11-33419968-abS928USQS6DZF2`, `TERMUX_VERSION=0.118.3`, RAM `10Gi` total / `15Gi` swap, `/data/user/0` has **94G free**. Primary model `Qwen3.5-4B-Q4_K_M.gguf` = `2,740,937,888` bytes. | `free -h`, `df -h`, `uname -a`, `getprop`, `ls -la ~/models/...` |
| 0.23 | SHA-256 throughput measured on this device: 84,106,624 B in **160 ms** → ≈ 525 MB/s. Hashing the 2.74 GB primary model therefore costs ≈ **5.2 s** of pure disk+CPU. It must not run on every process start. | live timing, 2026-09-03 |
| 0.24 | Existing Aigentik free-text log volume is **130 KB – 672 KB per day** across the last 7 days. Useful ground truth for the volume estimate in §6. | `ls -la ~/Codey-Aigentik/data/logs/` |
| 0.25 | `install.sh` installs commands at three places: `chmod +x` block (lines 334-339), `setup_symlinks()` loop (line 370) and its success message (375), and the PATH-verification block (429-430). | `install.sh` |

---

## 1. Reused / wrapped vs. built new

### 1.1 Reused and wrapped (not rebuilt)

| Existing component | How the telemetry layer uses it |
|---|---|
| `core/resource_gate.py` — `GateDecision`, `DispatchDecision`, `TripDecision`, `ContextBudgetDecision`, `ResourceSnapshot` | **Serialized, never reimplemented.** A recorder function takes the dataclass instance and `dataclasses.asdict()`s it into the category-B/C record body. The gate keeps sole authority over what a decision *is*; the telemetry layer only writes down what it already decided. **Target: zero edits to `core/resource_gate.py`.** |
| `core/resource_gate.py` — `sample_cpu_percent`, `sample_temperature_c`, `get_resource_snapshot`, `get_cpu_history`, `get_temp_history`, `read_zram_stats`, `compute_zram_compression_ratio` | Category C reads the *already-composed* `ResourceSnapshot` the daemon builds on its 30 s watchdog tick. **No new sampler, no new timer, no second cadence.** The honest-null contract of these functions (`sample_cpu_percent` returns `None`, never `0.0` — `core/resource_gate.py:551-570`) is inherited verbatim: a `None` here becomes a schema null carrying reason `proc_stat_permission_denied`. |
| `core/resource_gate.py` — `is_interactive_session_active()` / `is_tui_session_active()` | Category D reads this signal. Records **transitions only** (see §1.4). |
| `core/thermal.py` — `start_inference()`, `end_inference()`, `get_thermal_status()`, `is_inference_active()` | Category C's continuous-inference duration counter. Recorded as `inference_seconds_this_run`, **never** as a lifetime counter — fact 0.19. |
| llama-server's own `timings` block | The single source for prefill and generation throughput. Wall-clock arithmetic is recorded *separately and additionally* (`wall_ms`), never substituted for the server's numbers. Where `timings` is absent, the throughput fields are null with reason `server_timings_absent` — not back-computed. |
| `core/resource_bus.py`'s `resource_leases` table | **Read-only, offline.** `codey-metrics` can join lease rows into an export for cross-checking, but the telemetry layer never writes to `resource_bus.db`. Its rows are updated in place (status transitions) and therefore are not an immutable ledger; treating them as one would be a provenance error. |
| `~/.codeyOS/llama-server.log` | **Deliberately not depended on.** It is free-text and truncated on every reload (fact 0.9). Everything category A needs is available structurally from the HTTP response (facts 0.4–0.8). This removes the only reason to touch `loader_v2.py`'s log handling. See §8 item 7. |
| `install.sh` | Extended (rule 11) to `chmod +x` and symlink the new `codey-metrics` command at the three sites in fact 0.25. |

### 1.2 Built new (nothing equivalent exists)

- The append-only, schema-versioned, provenance-tagged event store itself
  (`telemetry/store.py`, `telemetry/envelope.py`, `telemetry/schema/`).
- Category **G** run provenance — nothing writes any of it today.
- Category **D** co-tenancy events — the detector runs but nothing records it.
- Category **E** durable task outcomes — `ccos/core/task_blackboard.py` is
  explicitly ephemeral (`ON DELETE CASCADE`); `core/state.py`'s
  `task_queue` rows are *mutated* through their lifecycle
  (`try_claim_task` → `start_task` → `complete_task`/`fail_task`), so the
  intermediate states are destroyed. An immutable per-transition record
  is genuinely new.
- Category **A** with correlation IDs, role/backend/thinking-mode tags,
  and durability across restarts.
- Category **F**'s denominator (the pass / not-applicable counterparts).
- The `codey-metrics` CLI.
- The cross-language schema mechanism.

### 1.3 Conflict 1 — `performance_tracker` / `ccos_memory.db` entanglement

**Resolution: bypass entirely. The telemetry layer will contain zero
imports from `ccos.*`, enforced by a test.**

Reasoning, in order of weight:

1. **Rule-1 hazard.** `cap_metrics` is not just written by gated modules,
   it is *read by them to decide changes* — `capability_optimizer` and
   `goal_engine` both consume it (fact 0.20). A telemetry writer feeding
   that table would be feeding the input of gated decision logic. Even
   with the gate closed, that is a wiring relationship this project has
   an explicit standing rule against creating.
2. **Import-graph contamination.** `get_performance_tracker()` is a
   module-level singleton in `ccos.core.performance_tracker`. Importing
   it from a module that runs on the daemon's hot path drags the CCOS
   package into that import graph. A future change inside CCOS could then
   affect telemetry availability — and, worse, the telemetry layer could
   become a reason someone argues a gated module "needs" to be importable.
3. **Schema mismatch.** `cap_metrics` has no `schema_version`, no
   `run_id`, no provenance columns, and its grain is *per capability*,
   not per request. It cannot carry the grant's provenance requirement
   without being redesigned, at which point it is a new store anyway.
4. **Mutability.** `ccos_memory.db` is a live, mutable operational DB.
   The evidence store must be append-only.

**Concrete enforcement:** `tests/test_telemetry_no_ccos_imports.py` walks
every module under `telemetry/` with `ast`, collects every `Import` /
`ImportFrom` node (including function-local lazy imports, which this
codebase uses heavily), and asserts none resolves to a name starting
`ccos.`. It is a static check, so it holds even for code paths that never
execute in tests.

**If Ish later wants CCOS capability metrics in the grant dataset:** they
are pulled by an *offline exporter* inside `codey-metrics export`, which
opens `ccos_memory.db` read-only (`file:...?mode=ro`) at export time,
tags the rows as `source: "ccos_cap_metrics"`, `derived: true`, and never
writes back. That keeps the read path one-directional and out of the
daemon process entirely.

### 1.4 Conflict 2 — Aigentik's 30-day `pruneOldLogs`

**Resolution: no change to `logger.js` is required, and none will be
made. The conflict is avoided structurally, plus one active interlock.**

Fact 0.14 is the key: `pruneOldLogs()` iterates `readdirSync(logsDir)`
and unlinks only entries where
`file.startsWith('aigentik-') && file.endsWith('.log')`. It is
double-filtered by both directory and filename. The telemetry store lives
at `~/.codeyOS/metrics/` with filenames like
`inference.<run_id>.jsonl` — a different directory *and* a
non-matching name. `pruneOldLogs` provably cannot reach it.

Relying on that silently would be fragile, so two things are added:

- **Interlock (active).** `telemetry.mjs` resolves its own store root and
  Aigentik's `config.paths.logs_dir` at init. If the metrics root is
  equal to, or nested inside, `logs_dir`, the JS writer **refuses to
  initialize**, emits a single `meta` record with
  `event_type: "writer_disabled"`,
  `reason: "metrics_root_inside_prunable_logs_dir"`, and thereafter
  no-ops. Records are then visibly missing rather than silently deleted
  30 days later — which is the difference between a gap you can report in
  a grant and a dataset you can't trust.
- **Test (passive).** `__tests__/telemetry.test.js` creates a temp
  metrics root plus a temp logs dir, writes records, runs
  `log.pruneOldLogs(0)` (retention zero — maximally aggressive), and
  asserts every telemetry file still exists. This pins the guarantee
  against a future change to `pruneOldLogs`'s filter.

**Also noted:** Aigentik's own `aigentik-*.log` files *are* still pruned
at 30 days, and they contain the historical `Discarding ungrounded
address extraction` warnings. Any pre-existing grounding-reject history
older than 30 days is already gone and is not recoverable. This is a
direct argument for shipping category F first (§7).

---

## 2. Schema

### 2.0 The shared envelope

Every record in every category, in both languages, is a single-line JSON
object with these fields at the top level. Category-specific fields live
under `body`.

| Field | Type | Unit / format | Notes |
|---|---|---|---|
| `schema_version` | int | — | Increments on any definition change. Old records are never rewritten. |
| `schema_sha256` | string | 12 lowercase hex chars | First 12 of the SHA-256 of the `v<N>.json` file that produced this record. Makes cross-repo schema drift **self-evident per record**, not just detectable by inspection. |
| `event_id` | string | 32 lowercase hex | `uuid4().hex`. Idempotency key for export/dedupe. |
| `run_id` | string | 16 lowercase hex | Identifies one *process*. Points at the category-G record. |
| `boot_id` | string | UUID | From `/proc/sys/kernel/random/boot_id` (fact 0.3). Groups all runs from one device boot. Null + reason if unreadable. |
| `seq` | int | — | Per-run monotonic counter starting at 0. A gap in `seq` within a run is proof of a dropped record. |
| `ts_wall` | float | Unix seconds, UTC | Human-orderable. Android wall clock can step (NTP/timezone), so this is **not** used for durations. |
| `ts_mono` | float | seconds since process start | `time.monotonic()` / `performance.now()/1000`. **All durations are derived from this**, never from `ts_wall` deltas. |
| `category` | string | enum | `inference` \| `gate` \| `device` \| `cotenancy` \| `task` \| `extraction` \| `provenance` \| `meta` |
| `event_type` | string | enum per category | See each category below. |
| `emitter` | string | enum | `codey-os.daemon` \| `codey-os.tui` \| `codey-os.core-api` \| `codey-os.plannd` \| `codey-os.loader` \| `aigentik` |
| `pid` | int | — | OS pid of the emitting process. |
| `correlation_id` | string \| null | 32 hex | Links A ↔ B ↔ E ↔ F for one logical request. Null + reason when the call site has no ambient correlation context yet. |
| `nulls` | object | `{field_name: reason_code}` | **Present only when non-empty.** See 2.0.1. |
| `body` | object | — | Category payload. |

**Record size cap:** 8,192 bytes serialized. A record exceeding it has its
longest string fields truncated to fit, and gains
`nulls: {"<field>": "truncated_oversize_record"}` plus
`body._truncated_fields: [...]`. Nothing is ever dropped for size alone.

#### 2.0.1 The honest-null contract (checkable, not aspirational)

> A field may be `null` **only if** its name appears as a key in `nulls`
> with a non-empty reason code. A `null` without a reason is a schema
> violation.

`codey-metrics doctor` scans for violations and reports a count. This
turns "we recorded honest nulls" from a claim into a verifiable property
of the dataset — which is exactly what a grant reviewer needs.

Reason codes (initial closed set; additions bump `schema_version`):

`proc_stat_permission_denied` · `proc_uptime_permission_denied` ·
`thermal_zone_unreadable` · `battery_read_failed` ·
`battery_read_timeout` · `zram_stats_unavailable` ·
`server_timings_absent` · `server_usage_absent` ·
`call_site_not_yet_tagged` · `model_sha256_not_computed` ·
`git_command_unavailable` · `remote_backend_no_local_metrics` ·
`state_store_unreadable` · `truncated_oversize_record` ·
`value_redacted_by_policy`

Precedent followed: `can_dispatch_task()` records "cpu_percent
unreadable, gate open" rather than implying CPU was confirmed low
(`core/resource_gate.py:2408-2418`).

---

### 2.A Inference events — `category: "inference"`

`event_type`: `completion` (one record per completion request, emitted
after the response is fully consumed) · `completion_failed`.

| Field (`body.`) | Type | Unit | Source |
|---|---|---|---|
| `role` | string \| null | enum: `coder`, `planner`, `summarizer`, `embed`, or an Aigentik task type (`email_reply`, `sms_reply`, `intake_classify`, `contact_extract`, `subcontractor_extract`, `customer_intake`, `recruiter_qualify`, `tone_detect`, `acknowledgment`, `content_gen`, `command_interpret`, `warmup`) | Call site. Null + `call_site_not_yet_tagged` until that site is tagged. |
| `thinking_mode` | bool \| null | — | `chat_template_kwargs.enable_thinking` actually sent. |
| `backend` | string | `local` \| `gemini` \| `vertex` \| `openrouter` \| `unlimitedclaude` \| `core_proxy` | Resolved at call time. |
| `model_file` | string \| null | absolute path | `MODEL_PATH` for local; null + `remote_backend_no_local_metrics` for remote. |
| `model_quant` | string \| null | e.g. `Q4_K_M` | Parsed from the GGUF filename; null if unparseable. |
| `model_sha256` | string \| null | 64 hex | From the digest cache (§3, fact 0.23). Null + `model_sha256_not_computed`. |
| `n_ctx` | int \| null | tokens | `resolve_effective_n_ctx()` result actually in force. |
| `prompt_tokens` | int \| null | tokens | `timings.prompt_n`, else `usage.prompt_tokens`. |
| `completion_tokens` | int \| null | tokens | `timings.predicted_n`, else `usage.completion_tokens`. |
| `cached_prompt_tokens` | int \| null | tokens | `timings.cache_n` (fact 0.5). |
| `prefix_cache_hit` | bool \| null | — | `cached_prompt_tokens > 0`. Derived, and the raw count is kept alongside. |
| `prefill_tps` | float \| null | tokens/s | `timings.prompt_per_second` — **the server's own number** (fact 0.4). |
| `generation_tps` | float \| null | tokens/s | `timings.predicted_per_second` — server's own number. |
| `prefill_ms` | float \| null | ms | `timings.prompt_ms`. |
| `generation_ms` | float \| null | ms | `timings.predicted_ms`. |
| `prompt_per_token_ms` | float \| null | ms | `timings.prompt_per_token_ms`. |
| `predicted_per_token_ms` | float \| null | ms | `timings.predicted_per_token_ms`. |
| `ttft_ms` | float \| null | ms | Streaming only: `ts_mono` at first content chunk minus request start. Null + `server_timings_absent` on the blocking path (no first-token boundary exists there — stated rather than faked). |
| `wall_ms` | float | ms | `ts_mono` delta across the whole call. Recorded **in addition to**, never instead of, the server figures. |
| `queue_wait_ms` | float \| null | ms | Time spent inside `wait_and_reserve_context_budget()` before admission. |
| `finish_reason` | string \| null | `stop` \| `length` \| `tool_calls` | `choices[0].finish_reason` (fact 0.6). |
| `interactive` | bool | — | `is_interactive_session_active()` at request start. Distinguishes interactive from background dispatch. |
| `server_request_id` | string \| null | — | llama-server's `id` (`oaicompat_cmpl_id`) — an independent server-side correlation handle. |
| `server_fingerprint` | string \| null | — | `system_fingerprint` = `llama_build_info()`; pins the llama.cpp build per request. |
| `stream` | bool | — | Whether the SSE path was used. |
| `max_tokens_requested` | int | tokens | — |
| `prompt_sha256` | string \| null | 64 hex | Content-free identity of the prompt. **See §8 item 3 — needs Ish's decision before implementation.** |
| `prompt_chars` | int | characters | Cheap size proxy that leaks no content. |
| `message_count` | int | — | Length of the `messages` array. |
| `error_class` | string \| null | — | On `completion_failed`: exception class name only, never the message (messages can embed prompt text). |

---

### 2.B Admission and dispatch decisions — `category: "gate"`

`event_type`: `can_admit` · `can_dispatch_task` ·
`reserve_context_budget` · `should_trip_shutdown`.

**Denials are recorded exactly as fully as admissions** — same fields,
same detail. That is the whole point; today only refusals leave a trace,
and even those are free text.

Common `body` fields:

| Field | Type | Unit | Notes |
|---|---|---|---|
| `decision` | object | — | `dataclasses.asdict()` of the actual `GateDecision` / `DispatchDecision` / `ContextBudgetDecision` / `TripDecision`. **Verbatim, no reshaping** — the gate stays the authority on its own field names. |
| `snapshot` | object \| null | — | `asdict()` of the `ResourceSnapshot` the decision was computed from, when the call site has one (`can_dispatch_task` always; `can_admit` has `meminfo` instead). |
| `meminfo` | object \| null | bytes | For `can_admit`: the `read_meminfo()` dict actually passed in. |
| `reason` | string | — | Lifted out of the decision object for cheap querying; also still present inside `decision`. |
| `admitted_via_swap` | bool \| null | — | From `GateDecision.admitted_via_swap`. |
| `dispatched_via_swap` | bool \| null | — | From `DispatchDecision.dispatched_via_swap`. |
| `swap_bytes_claimed` | int \| null | bytes | From `GateDecision.swap_bytes_claimed`. |
| `budget_ceiling_exceeded` | bool \| null | — | From `GateDecision`. |
| `call_site` | string | — | e.g. `daemon._check_dispatch_gate`, `loader_v2.ModelLoader.load_primary`, `inference_hybrid.infer`, `plannd.request_plan`, `api.routes.ai_chat`. |
| `retry_count` | int \| null | — | `reserve_context_budget` only: how many retries the wrapper made. |
| `wait_ms` | float \| null | ms | `reserve_context_budget` only: total time inside the wrapper. |
| `repeat_count` | int | — | See edge-triggering below. `1` for a state-change record. |
| `dedup_window_ms` | float \| null | ms | Span this record's `repeat_count` covers. |

**Edge-triggered recording (this is load-bearing, not an optimization).**
Fact 0.12: `_check_dispatch_gate()` can be evaluated **twice per second**.
Recording every evaluation would produce **172,800 gate records/day**
≈ **155 MB/day** from that one call site alone, which is (a) a real I/O
and storage cost on a phone, and (b) scientifically useless — 172,800
copies of "deferred: interactive session active" is one fact, not 172,800
observations.

Rule, applied per `call_site`:

1. Emit a record when the tuple `(allowed/admitted, reason)` differs from
   the previous emission for that call site.
2. Otherwise, emit a **heartbeat** record at most once per 60 s carrying
   `repeat_count` = evaluations collapsed since the last emission and
   `dedup_window_ms` = the span covered.
3. `repeat_count` makes the collapse lossless *for rate reconstruction*:
   summing `repeat_count` over a window recovers the true evaluation
   count exactly.

This is the single largest volume decision in the design and the reason
the layer fits in ~6.75 MB/day (§6) instead of ~160 MB/day.

**Where the instrumentation goes (passivity — see §5.1).**
`reserve_context_budget()` runs inside a cross-process `flock`
(fact 0.13). Instrumenting *inside* it would extend the lock hold time
for every other process on the device — that is a control-flow change,
not passive measurement. Therefore category-B records for the context
budget are emitted at the **caller boundary** —
`wait_and_reserve_context_budget()`'s return and its call sites — as
**one record per wrapper call** carrying `retry_count` and `wait_ms`,
never one record per 2 s retry.

---

### 2.C Device state — `category: "device"`

`event_type`: `sample` (every daemon watchdog tick, ≈ 30 s) ·
`thermal_throttle` (edge-triggered) · `counter_reset`.

| Field (`body.`) | Type | Unit | Source |
|---|---|---|---|
| `ram_total_bytes` | int | bytes | `ResourceSnapshot.ram_total_bytes` |
| `ram_headroom_bytes` | int | bytes | `ResourceSnapshot.ram_headroom_bytes` (`MemAvailable`-derived) |
| `mem_free_bytes` | int \| null | bytes | `read_meminfo()['MemFree']` |
| `mem_available_bytes` | int \| null | bytes | `read_meminfo()['MemAvailable']` |
| `swap_total_bytes` | int | bytes | `ResourceSnapshot.swap_total_bytes` |
| `swap_free_bytes` | int | bytes | `ResourceSnapshot.swap_free_bytes` |
| `swap_used_bytes` | int | bytes | `swap_total - swap_free` (derived; both inputs kept) |
| `zram_compression_ratio` | float \| null | ratio (orig/compressed) | `compute_zram_compression_ratio()`; null + `zram_stats_unavailable` |
| `zram_orig_data_bytes` | int \| null | bytes | `read_zram_stats()` raw |
| `zram_compr_data_bytes` | int \| null | bytes | `read_zram_stats()` raw |
| `temperature_c` | float \| null | °C | `ResourceSnapshot.temperature_c`; null + `thermal_zone_unreadable` |
| `cpu_percent` | float \| null | % 0–100 | **Always null on this device**, reason `proc_stat_permission_denied` (fact 0.1). Inherited, not fixed. |
| `battery_percent` | int \| null | % 0–100 | `ResourceSnapshot.battery_percent`; null + `battery_read_failed`/`battery_read_timeout` |
| `battery_charging` | bool | — | `ResourceSnapshot.battery_charging` |
| `queue_pending` | int | tasks | `ResourceSnapshot.queue_pending` |
| `queue_running` | int | tasks | `ResourceSnapshot.queue_running` |
| `inference_active` | bool | — | `core.thermal.is_inference_active()` |
| `inference_seconds_this_run` | float | s | `ThermalManager._total_inference_sec`. **Named `_this_run` deliberately** — it resets on daemon restart (fact 0.19) and must never be read as a lifetime total. |
| `throttle_level` | string \| null | — | From `get_thermal_status()` |
| `device_uptime_sec` | null | s | **Always null**, reason `proc_uptime_permission_denied` (fact 0.2). Recorded as a named null rather than omitted, so the restriction is visible in the dataset. |

`thermal_throttle` records carry `{from_level, to_level, temperature_c,
inference_seconds_this_run}` and are emitted only on a level change.

Note: although `device`'s `event_type` enum lists `counter_reset`, the
actual `counters_reset`/`reason` body fields for this event type live
under **`category: "meta"`** (§2.meta / `telemetry/schema/v2.json`), not
`device`. It is emitted at run start listing every counter that reset
with this process (`["thermal.total_inference_sec", "telemetry.seq",
"telemetry.dropped_count"]`) — satisfying constraint 6 by *recording the
reset explicitly as an event* rather than pretending continuity.

---

### 2.D Co-tenancy events — `category: "cotenancy"`

`event_type`: `interactive_transition` · `dispatch_refused_human_present`
· `deferral_resolved`.

**Correction to the spec (fact 0.10):** there is no GUI detector. The
`{tui, gui_client, both}` split is not implementable — `is_gui_client_connected()`
was deliberately removed on 2026-09-02 because it had a fail-open trap.
The design records `detector: "tui"` with the field present (so the schema
survives a future GUI/dashboard detector without a version bump) and
`detector_available: ["tui"]`. Flagged in §8 item 1.

**Correction to the spec (fact 0.11):** there is no preemption. The gate
is a pre-claim check; in-flight background work is never suspended, and
task state trivially "survives" because the row is never claimed in the
first place. What *is* real and measurable is **deferral**: the wall time
between a task's first refusal and its eventual dispatch. Flagged in §8
item 2.

| Field (`body.`) | Type | Unit | Notes |
|---|---|---|---|
| `detector` | string | `tui` | Which detector fired. |
| `detector_available` | array[string] | — | `["tui"]` today. Documents what *could* have fired. |
| `active` | bool | — | New state after the transition. |
| `previous_active` | bool | — | State before. |
| `live_session_pids` | array[int] | — | PIDs from `TUI_SESSIONS_DIR` at transition time. |
| `session_count` | int | — | `len(live_session_pids)`. |
| `state_duration_ms` | float | ms | How long the *previous* state held, from `ts_mono`. |
| `refused_task_id` | int \| null | — | `dispatch_refused_human_present` only. |
| `refusal_reason` | string \| null | — | `DispatchDecision.reason` verbatim. |
| `deferral_ms` | float \| null | ms | `deferral_resolved` only: first-refusal → dispatch, per task id. |
| `deferral_refusal_count` | int \| null | — | How many gate evaluations refused this task before it ran. |
| `task_state_preserved` | bool \| null | — | `deferral_resolved` only. Always `true` under the current pre-claim design; recorded rather than assumed so that if a real preemption path is ever added, the field is already there and a `false` would be visible. |

---

### 2.E Task outcomes — `category: "task"`

`event_type`: `task_started` · `task_step` · `task_finished`.

Three event types rather than one row, because `core/state.py`'s
`task_queue` **mutates** rows through the lifecycle — an immutable ledger
has to record the transitions, not the final state.

| Field (`body.`) | Type | Unit | Source |
|---|---|---|---|
| `task_id` | int | — | `task_queue.id` |
| `task_type` | string | `planner` \| `direct` \| `planning_expansion` | Which branch of `_process_planner_tasks()` |
| `needs_planning` | bool | — | `task_queue.needs_planning` |
| `started_ts_wall` / `finished_ts_wall` | float \| null | Unix s | — |
| `duration_ms` | float \| null | ms | `ts_mono` delta |
| `terminal_status` | string \| null | `done` \| `failed` \| `timeout` \| `cancelled` \| `superseded_by_plan` | `superseded_by_plan` covers `core/daemon.py:1349-1351`, where the raw row is completed because it expanded into N steps — a case that would otherwise be miscounted as a success. This value is only reachable by instrumenting `core/daemon.py` directly (T8); `_execute_task()` (`core/task_executor.py`, T7) is never even called on that path, so T7 alone cannot emit it. |
| `step_count` | int \| null | — | Agent-loop steps actually taken (`core/agent.py:1582-1583`) |
| `max_steps` | int \| null | — | The ceiling in force (`core/agent.py:1549, 1580`) |
| `hit_max_steps` | bool \| null | — | `core/agent.py:2120` |
| `tools_called` | object \| null | `{tool_name: count}` | Aggregated per task, not one record per call |
| `tool_call_total` | int \| null | — | Sum of the above |
| `retries` | int \| null | — | `task_queue.retry_count` |
| `escalated` | bool \| null | — | Whether `core/peer_cli.escalate_or_park()` was reached |
| `escalation_reason` | string \| null | `retries_exhausted` \| `patch_failure` \| `null` | `core/agent.py:1926-1963` distinguishes these two paths |
| `escalation_outcome` | string \| null | `peer_cli` \| `parked` \| `skipped` | — |
| `inference_ms_total` | float \| null | ms | Summed `wall_ms` of every category-A record sharing this `correlation_id` — **computed at rollup time from the A records, not tracked separately.** One source of truth. |
| `inference_call_count` | int \| null | — | Same derivation |
| `error_class` | string \| null | — | Exception class name only, no message |
| `timeout_sec` | int \| null | s | The `task_timeout` in force |

---

### 2.F Extraction and verification events (Aigentik) — `category: "extraction"`

**Highest implementation priority.** `event_type`:
`extraction_attempt` · `grounding_check` · `deterministic_bypass`.

The denominator is the entire point. Today only rejections are logged
(fact 0.16), so no pass rate is computable, and pre-existing rejection
history older than 30 days has already been pruned (§1.4).

#### The four-outcome grounding taxonomy

Reading `isAddressGrounded()` (`llama.js:536-541`) together with its two
call sites (`:554`, `:726`) gives **four** behaviourally distinct
outcomes, of which the current code logs **one**:

| Outcome code | Condition | Logged today? |
|---|---|---|
| `not_applicable_no_value` | The model returned no address at all. Short-circuited by `parsed.address &&` at the call site — `isAddressGrounded()` is never invoked. | No |
| `passed_no_numeric_token` | An address was returned, but `String(address).match(/\d{2,}/g)` found no 2+-digit run (e.g. a bare city/state). The function returns `true` **without verifying anything** — the comment says "let it through". | No |
| `passed_numeric_match` | Numeric tokens present and at least one appears verbatim in the source text. A genuinely verified pass. | No |
| `rejected` | Numeric tokens present, none found in the source. The value is discarded. | **Yes** — `log.warn(...)` |

`passed_no_numeric_token` and `passed_numeric_match` being conflated
matters for the grant: the first is an *unverified* pass, the second is a
*verified* one. Reporting them as a single "pass rate" would overstate the
verification rate. They are recorded separately.

#### How this is instrumented without changing behaviour

`isAddressGrounded()` is left **byte-identical**. A new pure sibling,
`classifyAddressGrounding(address, sourceText) → outcome_code`, is added
and called at the two call sites *in addition to* the existing check,
purely to produce the record.

Rationale for duplication over refactor: rewriting `isAddressGrounded()`
as a thin wrapper over the classifier would change its behaviour for
falsy input — today `!address` returns `false`, whereas the natural
classifier result is `not_applicable_no_value` (a non-reject). The two
call sites guard with `parsed.address &&` so the case is unreachable
*from them*, but the function is exported and could acquire another
caller. A live extraction guard on customer data is not the place to take
that risk for tidiness. The cost is one extra short regex per extraction.
A unit test asserts
`classifyAddressGrounding(a, s) === 'rejected'  ⟺  !isAddressGrounded(a, s)`
for all non-falsy inputs, so the two cannot drift silently.

#### Fields

`extraction_attempt`:

| Field (`body.`) | Type | Unit | Notes |
|---|---|---|---|
| `extractor` | string | `contact_details` \| `subcontractor_details` \| `customer_intake` \| `recruiter_qualification` \| `scheduling_intent` | — |
| `requested_fields` | array[string] | — | The `fields` argument / schema keys |
| `returned_fields` | array[string] | — | Keys actually present after parse |
| `null_fields` | array[string] | — | Keys returned as `null` |
| `dropped_schema_echo_fields` | array[string] | — | Keys deleted because the model echoed the type name (`llama.js:558-562`) — currently a silent failure mode with no counter |
| `parse_ok` | bool | — | Whether `extractJson()` produced an object |
| `parse_error_class` | string \| null | — | Class name only |
| `source_chars` | int | characters | Length of the input text — no content |
| `model_backend` | string | — | Resolved provider |

`grounding_check`:

| Field (`body.`) | Type | Notes |
|---|---|---|
| `field` | string | `address` or `property_address` |
| `outcome` | string | One of the four codes above |
| `numeric_tokens_in_value` | int | `match(/\d{2,}/g)?.length ?? 0` |
| `numeric_tokens_matched` | int | How many appeared in the source |
| `value_sha256` | string \| null | Content-free identity of the extracted value (§8 item 3) |
| `value_chars` | int | Length only |
| `source_chars` | int | Length only |
| `action_taken` | string | `kept` \| `discarded` |

`deterministic_bypass` — the cost-avoidance claim:

| Field (`body.`) | Type | Notes |
|---|---|---|
| `rule_id` | string | Which deterministic rule matched |
| `rule_source` | string | e.g. `subcontractor-form.parseApplication`, `email-rules`, `sms-rules`, `do-not-contact` |
| `would_have_called_model` | bool | Whether an LLM call was genuinely avoided (vs. a rule that runs alongside one) |
| `estimated_tokens_avoided` | int \| null | From the measured median `prompt_tokens + completion_tokens` for the equivalent extractor over the trailing 7 days (computed at rollup, never guessed inline) |
| `estimated_ms_avoided` | float \| null | Same derivation from median `wall_ms` |

The two `estimated_*` fields are **not written into raw records at all.**
They are derived quantities — a median over the trailing 7 days of
category-A records — and a derived value has no place in an immutable
observation. They exist only as columns in `rollups.db`, computed by the
rollup pass, and are labelled `derived: true` there. A raw
`deterministic_bypass` record contains only what was directly observed:
which rule matched, where it came from, and whether a model call was
genuinely avoided.

---

### 2.G Run provenance — `category: "provenance"`

`event_type`: `run_start` (written once, first record of every run) ·
`run_end` (best-effort, on clean shutdown).

Written to `runs/<run_id>.json` **and** as the first line of every
category file for that run, so a single-category export is
self-describing without a join.

| Field (`body.`) | Type | Unit | Notes |
|---|---|---|---|
| `run_id` | string | 16 hex | — |
| `boot_id` | string \| null | UUID | fact 0.3 |
| `emitter` | string | enum | Which process |
| `pid` | int | — | — |
| `started_ts_wall` | float | Unix s | — |
| `git_commit_sha` | string \| null | 40 hex | `git rev-parse HEAD`, 2 s timeout; null + `git_command_unavailable` |
| `git_dirty` | bool \| null | — | `git status --porcelain` non-empty |
| `git_dirty_file_count` | int \| null | — | Line count — a bare `dirty: true` is not enough provenance for a grant |
| `git_branch` | string \| null | — | — |
| `repo` | string | `Codey-OS` \| `Codey-Aigentik` | Both repos emit provenance |
| `device_model` | string \| null | — | `getprop ro.product.model` → `SM-S928U` |
| `android_release` | string \| null | — | `getprop ro.build.version.release` → `16` |
| `android_sdk` | int \| null | — | `getprop ro.build.version.sdk` |
| `kernel_version` | string \| null | — | `uname -r` |
| `termux_version` | string \| null | — | `$TERMUX_VERSION` → `0.118.3` |
| `python_version` / `node_version` | string \| null | — | Whichever applies |
| `ram_total_bytes` | int \| null | bytes | `MemTotal` |
| `swap_total_bytes` | int \| null | bytes | `SwapTotal` |
| `cpu_core_count` | int \| null | — | `resource_gate.get_cpu_core_count()` |
| `device_uptime_sec` | null | s | Always null + `proc_uptime_permission_denied` (fact 0.2) |
| `models` | array[object] | — | One entry per configured model: `{role, path, size_bytes, mtime_ns, sha256, sha256_source}` where `sha256_source ∈ {computed, cached, not_computed}` |
| `llama_server_bin` | string \| null | path | `LLAMA_SERVER_BIN` |
| `llama_build_info` | string \| null | — | `system_fingerprint` from the first completion of the run, backfilled into the rollup — not blocking on it at start |
| `llama_server_argv` | array[string] \| null | — | The exact spawn argv from `loader_v2` (this is the single most useful provenance artifact for reproducing a measurement, and it is currently only in a log file that gets truncated) |
| `env_overrides` | object | — | **Allow-list only.** See below. |
| `config_snapshot` | object | — | **Allow-list only.** See below. |
| `schema_version` / `schema_sha256` | int / string | — | Also in the envelope; repeated here so `runs/<id>.json` stands alone |

**Env and config are allow-listed, never dumped (fact 0.21).**
`OPENROUTER_API_KEY`, `UNLIMITEDCLAUDE_API_KEY`,
`CLOUDFLARE_TUNNEL_TOKEN` and Aigentik's `core_api.token` live in the
same environment/config. A permanent, immutable, exportable,
grant-attached store is the worst possible place for them, and the
append-only rule means a leak cannot be edited out afterwards.

Proposed allow-list (needs Ish's confirmation, §8 item 4):
`CODEY_N_CTX`, `CODEY_SWAP_ASSIST_ADMISSION`, `CODEY_7B_MMAP`,
`CODEY_7B_MLOCK`, `CODEY_BACKEND`, `CODEY_BACKEND_P`, `CODEY_MODEL`,
`CODEY_EMBED_MODEL`, `CODEY_PRIMARY_PORT`, `CODEY_EMBED_PORT`,
`CODEY_RECURSIVE`, `CODEY_SYMBOLIC`, `CODEY_SHUTDOWN_TRIP_AFTER_SEC`,
`CODEY_LLAMA_SERVER`, `CODEY_STATE_DIR`, `CODEY_TELEMETRY`, and the
resolved thread count (`allocate_threads()` result).

For secret-bearing names, only **presence** is recorded, as a boolean —
`{"openrouter_api_key_set": true}` — never the value, never a hash of the
value (a hash of a short token is a cracking target, not a redaction).

`config_snapshot` is an explicit projection: `MODEL_CONFIG` (temperature,
top_p, top_k, repeat_penalty, n_ctx, stop), `THERMAL_CONFIG`, the
resource-gate constants actually in force
(`MAX_CONCURRENT_MODEL_BUDGET_BYTES`, `DISPATCH_MIN_HEADROOM_BYTES`,
`DEVICE_CEILING_USABLE_FRACTION`, `REQUIRED_HEADROOM_FACTOR`,
`CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION`,
`CONTEXT_QUEUE_POLL_INTERVAL_SECONDS`). Anything not on the projection
list is not recorded, and `config_snapshot._policy` records which
allow-list version produced it.

---

### 2.meta — `category: "meta"`

`event_type`: `writer_started` · `writer_stopped` · `records_dropped` ·
`counter_reset` · `rotation` · `schema_mismatch` · `writer_disabled` ·
`emit_cost`.

| Field (`body.`) | Type | Unit | Notes |
|---|---|---|---|
| `dropped_total` | int | records | Cumulative for this run |
| `dropped_by_category` | object | `{category: count}` | Makes gaps attributable |
| `drop_reason` | string \| null | `ring_buffer_full` \| `write_failed` \| `serialize_failed` | — |
| `buffer_high_water` | int | records | Peak buffer occupancy this run |
| `flush_count` | int | — | — |
| `bytes_written` | int | bytes | This run |
| `emit_ns_p50` / `emit_ns_p95` / `emit_ns_max` | int | ns | The layer measuring its own hot-path cost (§5) |
| `counters_reset` | array[string] | — | `counter_reset` only |
| `reason` | string \| null | — | `writer_disabled` / `schema_mismatch` only |

`records_dropped` is emitted on the first drop and then at most once per
60 s. `emit_cost` is emitted once per 5 min. A run whose final record is
not `writer_stopped` is reported by `codey-metrics doctor` as
"terminated without clean shutdown — dropped-count for the final ≤60 s
window is unknown", which is an honest statement of an unknowable, not a
zero.

---

## 3. Storage layout and access

### 3.1 Layout

```
~/.codeyOS/metrics/
├── SCHEMA_VERSION                  # plain text: "1"
├── schema/
│   ├── v2.json                     # authoritative copy actually in use at runtime
│   └── v1.json                     # frozen, retained for historical-record validation
├── runs/
│   └── <run_id>.json               # category G, written once, never reopened for write
├── events/
│   └── <YYYY-MM-DD>/
│       ├── inference.<run_id>.jsonl
│       ├── gate.<run_id>.jsonl
│       ├── device.<run_id>.jsonl
│       ├── cotenancy.<run_id>.jsonl
│       ├── task.<run_id>.jsonl
│       ├── extraction.<run_id>.jsonl
│       └── meta.<run_id>.jsonl
├── archive/
│   └── <YYYY-MM>/<YYYY-MM-DD>.tar.gz
├── rollups.db                      # SQLite; DERIVED, rebuildable, not evidence
├── model_digests.json              # {path: {size, mtime_ns, sha256, computed_at}}
└── .rotate.lock                    # flock target for rotate/rollup
```

`~/.codeyOS/` is the established runtime-state root
(`utils/config.py:306`) and already holds `state.db`, `resource_bus.db`,
`restoricon.db`, and the log/PID files. Putting `metrics/` there matches
convention, is outside the git repo (no accidental commits of measurement
data), and is on the partition with 94 GB free (fact 0.22).

### 3.2 Why JSONL for events and SQLite only for rollups

Three reasons, in order of weight:

1. **Append-only is native to a file and is not native to SQLite.** A
   file opened `O_APPEND` cannot have an existing byte rewritten by the
   writer's own normal operation. SQLite rewrites pages in place, has
   `UPDATE`/`DELETE` available to any process that opens it, and
   `VACUUM` rewrites the whole file. "Immutable" would be a convention
   enforced by discipline rather than by the storage medium. For a store
   whose entire purpose is being credible evidence, the medium should do
   the enforcing.
2. **No cross-process write coordination is needed.** By putting
   `<run_id>` in the filename, **every file has exactly one writer for
   its whole life.** There is no shared-append interleaving question, no
   lock, no `busy_timeout`, no WAL contention with the four other SQLite
   DBs already on this device. This also means a telemetry write can
   never block on another process — which is constraint 2.
3. **Corruption is bounded to one line.** A torn write from a SIGKILL
   damages at most the final record; `codey-metrics doctor` reports it
   and every prior line still parses. A torn SQLite page can take the
   database.

SQLite *is* the right tool for rollups: aggregates are queried
interactively, need indexes, and are **derived and rebuildable** from the
raw JSONL and archives. `rollups.db` is therefore explicitly designated
**not evidence** — it is a cache. If it is ever lost or found
inconsistent, `codey-metrics rollup --rebuild` regenerates it from the
raw record set. (Confirmation requested, §8 item 9.)

This split also matches existing convention rather than inventing one:
`core/resource_bus.py` and `core/state.py` use SQLite for *mutable
operational state*, which is what they hold. Nothing in the repo
currently uses SQLite as an immutable ledger.

### 3.3 Cross-language schema mechanism

> **T10 migration complete (2026-09-10):** both repos now load
> `telemetry/schema/v2.json` (adds the `codey-os.cli` emitter value,
> additive-only — no other change from v1). `v1.json` is retained,
> frozen forever, so historical records keep validating;
> `telemetry/schema.py` carries `KNOWN_SCHEMA_SHA256_12` mapping every
> shipped version's hash for `doctor`. `v2.json` is the runtime schema
> in both repos.

The current-version schema file (`telemetry/schema/v2.json`) is the single
source of truth. It defines, per category: the field list, each field's
type, unit, nullability, and the closed set of enum values and null-reason
codes.

- **Python** (`telemetry/schema.py`) loads it with `json.load` at import,
  computes its SHA-256 once, and exposes `SCHEMA_VERSION`,
  `SCHEMA_SHA256_12`, and a cheap `validate(record)` used in tests and by
  `codey-metrics doctor` — **not** on the hot path.
- **JavaScript** (`telemetry.mjs`) loads `./telemetry/schema/v2.json` as
  raw bytes via `fs.readFileSync` (deliberately *not* an
  `import ... with { type: 'json' }` assertion — a re-serialized parsed
  object would not reproduce the original file bytes, so its hash would
  not match Python's; see `telemetry.mjs`'s own comment).

**The two repos hold byte-identical copies**, because Aigentik has no
configured path to Codey-OS (verified: `config.json` has `paths.data_dir`,
`logs_dir`, `conversations_dir`, and `core_api.base_url` — nothing
pointing at the Codey-OS tree), and hard-coding one would be a new
cross-repo coupling.

Drift is handled by making it **visible per record rather than merely
detectable**: every record carries `schema_sha256`. If the copies diverge,
records from the two repos carry different hashes and any analysis
immediately shows a mixed dataset. On top of that:

- A test on each side asserts its copy's SHA-256 equals a constant
  checked into both repos.
- `codey-metrics schema --verify` compares the two files directly when
  both are present on the device and prints a diff.
- Startup mismatch emits a `meta` / `schema_mismatch` record rather than
  failing — measurement continues, tagged.

(An alternative — Aigentik reading Codey-OS's file via a new
`paths.codey_os_dir` config key — is offered to Ish in §8 item 5.)

### 3.4 Model digest cache

Fact 0.23: hashing the 2.74 GB primary model costs ≈ 5.2 s of disk+CPU.
Doing that at every process start would be a real, recurring cost and
would evict useful page cache before a model load.

`model_digests.json` caches `{path: {size_bytes, mtime_ns, sha256,
computed_at}}`. At run start the layer stats the file; if `size_bytes`
and `mtime_ns` match the cache entry, the cached digest is used and
`sha256_source: "cached"` is recorded. On mismatch or a cold cache, the
hash is computed **on the background writer thread**, never on the
starting process's critical path, and the provenance record is amended by
a follow-up `provenance`/`run_start_amended` record (append-only: the
original is not edited). If it has not completed by run end, the field
stays null with reason `model_sha256_not_computed` — an honest null, not a
blocking wait.

### 3.5 `codey-metrics` CLI

A new executable at the repo root alongside `codey-start` / `codey-stop`,
implemented in `telemetry/cli.py`. **Default output is formatted for a
40-column phone terminal**: two-column key/value, no box drawing, no
table wider than 40 chars, values right-aligned and abbreviated
(`1.2G`, `48.3t/s`). `--wide` opts into full-width output; `--json` emits
machine-readable output for every subcommand.

| Subcommand | Does |
|---|---|
| `codey-metrics` (no args) → `summary` | Live summary: today's counts per category, median generation/prefill tok/s, gate admit vs deny counts, grounding pass/reject/N-A breakdown, current interactive state, store size on disk. |
| `codey-metrics export --from D --to D [--category C] [--format csv\|json\|jsonl]` | Date-range export. Reads raw JSONL and transparently reads inside `archive/*.tar.gz` for older ranges, so an export never depends on whether rotation has run. |
| `codey-metrics provenance [--run ID \| --latest \| --all]` | Prints a run's category-G record in full. |
| `codey-metrics status` | Schema version + hash, dropped-record counts (today / all-time / by category), buffer high-water, bytes written, last write timestamp per emitter, and which emitters have gone silent. |
| `codey-metrics doctor` | Integrity: nulls without a reason code, `seq` gaps within a run, unparseable trailing lines, schema-hash mismatches across records, runs with no `writer_stopped`, and orphan runs with no `run_start`. Exit code non-zero if any violation is found. |
| `codey-metrics rollup [--date D \| --rebuild]` | Builds/rebuilds `rollups.db`. Takes `.rotate.lock`. |
| `codey-metrics rotate [--dry-run]` | Compresses day directories older than the retention threshold. Takes `.rotate.lock`. **Contains no deletion path.** |
| `codey-metrics schema [--verify]` | Prints the active schema version/hash; `--verify` diffs the two repos' copies. |

`summary`, `export`, `provenance`, `status`, and `doctor` are read-only
and safe to run while everything else is running. `rollup` and `rotate`
take `~/.codeyOS/metrics/.rotate.lock` (`flock`, non-blocking, exits with
a clear message if held) and refuse to touch the current or previous
day's directory, so they can never race a live writer.

---

## 4. Every file created or modified

Rule-4 flags (`[R4]`) mark files whose modification requires an explicit
code-reviewer approval before commit. Rule-11 (`install.sh` currency) is
discharged by the one entry noted.

### 4.1 New files — Codey-OS (`/data/data/com.termux/files/home/Codey-OS/`)

| Path | Purpose (one line) |
|---|---|
| `telemetry/__init__.py` | Package init; re-exports the public `record_*()` emit API and the `CODEY_TELEMETRY` kill-switch flag. |
| `telemetry/schema/v2.json` | The versioned schema — single source of truth for field names, types, units, enums, and null-reason codes, in both languages. (`v1.json` retained alongside, frozen, for historical-record validation.) |
| `telemetry/schema.py` | Loads the current-version schema (`v2.json` as of T10), computes and exposes `SCHEMA_VERSION` / `SCHEMA_SHA256_12` / `KNOWN_SCHEMA_SHA256_12` (per-version hashes for `doctor`), and provides off-hot-path `validate(record)` for tests and `doctor`. |
| `telemetry/envelope.py` | Builds the shared envelope (`run_id`, `seq`, `ts_wall`/`ts_mono`, `boot_id`, `nulls` map) and enforces the 8 KiB record cap. |
| `telemetry/store.py` | Bounded ring buffer, background writer thread, `O_APPEND` JSONL writes, drop counting; every public entry point is exception-proof. |
| `telemetry/provenance.py` | Collects category G (git SHA/dirty/branch, device, kernel, Termux, RAM, model digests via cache, allow-listed env + config). |
| `telemetry/recorders.py` | The category A–G + meta `record_*()` functions that map domain objects (`GateDecision`, `ResourceSnapshot`, llama-server `timings`) into schema records. |
| `telemetry/rollup.py` | Builds/rebuilds `rollups.db` daily aggregates from raw JSONL and archives; derived and rebuildable, never authoritative. |
| `telemetry/rotate.py` | Compresses day directories older than the retention threshold into verified `.tar.gz` archives; contains no deletion path. |
| `telemetry/cli.py` | Implements `codey-metrics` subcommands (`summary`, `export`, `provenance`, `status`, `doctor`, `rollup`, `rotate`, `schema`) with 40-column default output. |
| `codey-metrics` | Repo-root executable entry point, matching the `codey-start`/`codey-stop` convention. |
| `tests/test_telemetry_schema.py` | Asserts the schema file's SHA-256 matches the checked-in constant and that every enum/null-reason code is closed. |
| `tests/test_telemetry_envelope.py` | Envelope shape, `seq` monotonicity, 8 KiB truncation behaviour, and the honest-null invariant (no null without a reason). |
| `tests/test_telemetry_store.py` | Ring-buffer bounding, drop counting, writer-thread isolation, and that a write failure never propagates to the caller. |
| `tests/test_telemetry_recorders.py` | Round-trips real `GateDecision`/`DispatchDecision`/`ContextBudgetDecision`/`ResourceSnapshot`/`timings` fixtures into valid records. |
| `tests/test_telemetry_provenance.py` | Allow-list enforcement — asserts no secret-bearing env var or config key can reach a record, and that model-digest caching keys on `(size, mtime_ns)`. |
| `tests/test_telemetry_no_ccos_imports.py` | Static `ast` walk over `telemetry/` asserting zero imports resolving to `ccos.*`, including function-local lazy imports (§1.3). |
| `tests/test_telemetry_rotation.py` | Rotation writes a verified archive before removing the source, never touches the current/previous day, and has no reachable delete path for archives. |

### 4.2 New files — Codey-Aigentik (`/data/data/com.termux/files/home/Codey-Aigentik/`)

| Path | Purpose (one line) |
|---|---|
| `telemetry/schema/v2.json` | Byte-identical copy of the Codey-OS schema; parity pinned by SHA-256 test on both sides. (`v1.json` retained alongside, frozen, for historical-record validation.) |
| `telemetry.mjs` | JS emitter — same envelope and store layout, async (non-blocking) appends, and the `pruneOldLogs` collision interlock (§1.4). |
| `__tests__/telemetry.test.js` | Schema-hash parity, envelope shape, prune interlock (`pruneOldLogs(0)` leaves records intact), and grounding-taxonomy/`isAddressGrounded` equivalence. |

### 4.3 Modified files — Codey-OS

| Path | Change (one line) | Sub-task | R4 |
|---|---|---|---|
| `utils/config.py` | Add `METRICS_DIR = CODEY_STATE_DIR / "metrics"`, the `CODEY_TELEMETRY` flag, and the category-G env allow-list constant. | T0 | No |
| `install.sh` | Add `codey-metrics` to the `chmod +x` block (~334-339), the `setup_symlinks()` loop and message (~370, 375), and the PATH check (~429) — rule 11. | T4 | No |
| `restoricon_core/api/routes.py` | Emit a category-A record from `/api/v1/ai/chat` after `resp_data` is parsed; no RBAC or gating change. | T3 | Review advised |
| `main.py` | Emit `run_start` provenance for the TUI process at startup. | T2 | No |
| `core/inference_hybrid.py` | Capture the full `timings` block, `usage`, `finish_reason`, `id`, `system_fingerprint`; `ttft_ms` at the existing `on_first_token` boundary; emit A + the B record for the budget wrapper (outside the lock). | T5 | **[R4]** |
| `core/plannd.py` | Emit A + B at the planner's `wait_and_reserve_context_budget()` call site (~line 562) with `role="planner"`. | T6 | **[R4]** |
| `core/task_executor.py` | Emit `task_started` / `task_finished` around `_execute_task()`. Does **not** cover the `superseded_by_plan` terminal status — that path never calls `_execute_task()`; see `core/daemon.py` row (T8). | T7 | **[R4]** |
| `core/agent.py` | Surface step count, tool-call tally, retry count, and escalation reason/outcome from the agent loop for category E. | T7 | **[R4]** |
| `core/daemon.py` | Edge-triggered gate records at `_check_dispatch_gate()`; category C on the existing 30 s watchdog tick; category D transitions and deferral tracking; `run_start`/`counter_reset` at start and `writer_stopped` in the shutdown `finally`. | T8 | **[R4]** |
| `core/loader_v2.py` | Emit `can_admit()` decision records at the model-load call sites and capture the exact `llama_server_argv` into run provenance. | T9 | **[R4]** |
| `core/resource_gate.py` | **No change.** Explicit non-goal — every decision object needed is already returned by its public API. | — | **[R4]** if ever touched |
| `docs/telemetry_layer_design.md` | This document. | — | No |

### 4.4 Modified files — Codey-Aigentik

| Path | Change (one line) | Sub-task |
|---|---|---|
| `llama.js` | Add the pure `classifyAddressGrounding()`; emit category F at the two existing call sites (`:554`, `:726`); add an optional third `meta` param to `chat()`. `isAddressGrounded()` left byte-identical. | T1 |
| `logger.js` | **No change.** The prune/metrics boundary is enforced by the interlock in `telemetry.mjs` and pinned by test, not by editing the logger (§1.4). | — |

### 4.5 New dependencies

**None.** JSONL, gzip, tar, SQLite, and `hashlib` are all Python stdlib;
the JS side uses `fs` and the `import ... with { type: 'json' }` syntax
already in use at `logger.js:4`. The only `install.sh` change is the
`codey-metrics` symlink (rule 11). If Ish selects zstd over gzip
(§8 item 6), that adds a `pkg install zstd` and a corresponding
`install.sh` edit.

---

## 5. Overhead: estimate, and the exact procedure to verify it

### 5.1 Passivity — where instrumentation may and may not go (constraint 1)

The following are stated as design constraints, not preferences. Two of
them mean the obvious instrumentation point is the **wrong** one.

| Site | Ruling |
|---|---|
| Inside `reserve_context_budget()` | **Forbidden.** It executes under a cross-process `flock` (fact 0.13). Any work added there extends the lock hold time for every other process's admission checks — a change to system behaviour, not an observation of it. Instrument at `wait_and_reserve_context_budget()`'s return and its call sites instead, one record per wrapper call. |
| Inside `_infer_streaming()`'s SSE chunk loop | **Forbidden.** It is a per-token loop with a 15 s socket read timeout. One record is emitted after the loop completes; `ttft_ms` is captured as a single `time.monotonic()` read at the existing `on_first_token` boundary, which already exists (`core/inference_hybrid.py:249-254`). |
| Inside `isAddressGrounded()` | **Forbidden** — see §2.F. Instrument the two call sites with a separate pure classifier. |
| Inside `can_admit()` / `can_dispatch_task()` / `should_trip_shutdown()` | **Forbidden as a source edit**; these are pure functions and the goal is zero edits to `core/resource_gate.py`. Instrument at the callers, which already hold the returned decision object. |
| `Daemon._check_dispatch_gate()` (`core/daemon.py:1152-1167`) | **Allowed** — it is the sole caller of `can_dispatch_task()` and already builds the snapshot. Emission is edge-triggered (§2.B). |
| Daemon watchdog tick (`core/daemon.py:995-1056`) | **Allowed** — category C rides the existing 30 s cadence. No new timer, no new thread for sampling. |
| `restoricon_core/api/routes.py` `/api/v1/ai/chat` | **Allowed** — `resp_data` is already fully parsed there (fact 0.18); emission is a dict read after the response is complete. |

**If instrumenting a path would change its control flow, the design does
not proceed with it** — the ruling above is how that requirement is
discharged, per site, in advance.

### 5.2 Expected cost

**RAM.** Per writing process: bounded ring buffer of 512 records
× ~700 B ≈ 350 KiB, plus the parsed schema dict and module code
≈ 250 KiB → **≈ 0.6 MiB per process**. Four writer processes (daemon,
Core API, Aigentik, TUI) → **≈ 2.4 MiB**, i.e. **≈ 0.023 %** of this
device's 10 GiB (fact 0.22). One background writer thread per Python
process (default 8 MiB *virtual* stack, a few KiB resident).

The ring buffer is bounded specifically because this device has crashed
from memory pressure before (CLAUDE.md rule 2). An unbounded queue that
grows when the disk is slow is exactly the wrong failure mode here; a
bounded buffer that drops and *counts* the drops is the right one.

**CPU.** `json.dumps` of a ~700 B record is on the order of 10–20 µs on
this class of core. At the steady-state rate implied by §6 (≈ 8,600
records/day ≈ 0.10 records/s) that is **microseconds per second** —
unmeasurable against inference. It is nevertheless *measured rather than
asserted*: the layer records its own `emit_ns` p50/p95/max into the `meta`
category every 5 minutes, so the cost claim is itself in the dataset.

**I/O.** ≈ 6.75 MB/day raw (§6), written as ≈ 281 KB/hour in
buffered flushes on a 2 s / 64-record cadence. **No `fsync` on the hot path.** `fdatasync` is called only
at rotation boundaries and at `writer_stopped`. Accepted consequence: a
hard power loss can lose up to ~2 s of buffered records — which is
recorded as an unclean-shutdown gap by `doctor` rather than silently
absorbed.

**A note on honesty:** CPU% on this device is unmeasurable (fact 0.1), so
the CPU cost of this layer **cannot be measured directly**. It is
inferred from (a) the throughput delta in the A/B procedure below and
(b) the layer's self-reported `emit_ns` histogram. The design says so
rather than reporting a fabricated CPU number.

### 5.3 The kill switch

`CODEY_TELEMETRY` (Python) / `AIGENTIK_TELEMETRY` (JS): `1` = enabled
(default), `0` = disabled. It is checked **once at module import** and
stored in a module-level boolean, so the disabled path is a single
predictable branch at the top of `record()` with no environment lookup,
no object construction, and no string formatting. The A and B arms of the
measurement below therefore differ by exactly one boolean.

### 5.4 Before/after measurement procedure (constraint 2)

This is the procedure to be run and its verbatim output logged before the
telemetry layer is considered live-verified.

**Rule-2 compliance:** one model-load cycle at a time; all N requests
batched into a single session; the cycle is not complete until
`ps aux | grep llama-server` shows nothing but the grep.

**Workload.** A fixed script issuing N = 20 identical, deterministic
completions (`temperature` pinned to 0, fixed prompt set of 5 prompts × 4
repeats) through `core/inference_hybrid.py` against the primary model at a
pinned `CODEY_N_CTX`, in one interactive session.

**Per-arm protocol:**

1. Record `free -h` verbatim.
2. Confirm no llama-server is running: `ps aux | grep llama-server` shows
   only the grep. Record verbatim.
3. Record `git rev-parse HEAD` and `git status --porcelain | wc -l`.
4. Start the daemon with the arm's `CODEY_TELEMETRY` value.
5. Record daemon `VmRSS` and `VmHWM` from `/proc/<daemon_pid>/status`,
   and `read_bytes`/`write_bytes` from `/proc/<daemon_pid>/io`.
6. Run the 20-request batch, capturing for each request the server's own
   `timings.prompt_per_second`, `timings.predicted_per_second`,
   `timings.cache_n`, and the client-side `ttft_ms` and `wall_ms`.
7. Record `/proc/<daemon_pid>/status` and `/proc/<daemon_pid>/io` again.
8. Record `free -h` verbatim.
9. Stop; confirm unload with `ps aux | grep llama-server`.
10. Record `du -sb ~/.codeyOS/metrics/` (0 for the OFF arm).

**Arm ordering: OFF, ON, OFF, ON, OFF, ON** — alternating, three of each.
Not three OFF then three ON. This device thermally throttles
(`THERMAL_CONFIG`, `should_trip_shutdown()`), so consecutive same-arm
runs would confound the arm effect with thermal drift. Alternation makes
drift affect both arms roughly equally, and the OFF-arm trend across runs
1/3/5 is itself the drift estimate.

**Reported comparisons:**

| Metric | Derived from |
|---|---|
| Δ median `predicted_per_second` | Server's own number, not wall clock |
| Δ median `prompt_per_second` | Server's own number |
| Δ median `ttft_ms` | Client-side monotonic |
| Δ daemon `VmHWM` | `/proc/<pid>/status` |
| Δ `write_bytes` per hour | `/proc/<pid>/io` |
| Bytes written to `metrics/` per hour | `du -sb` |
| `emit_ns` p50/p95/max | The layer's own `meta`/`emit_cost` records (ON arm only) |
| OFF-arm drift | Spread across OFF runs 1/3/5 — the confound floor |

**Proposed acceptance thresholds** (Ish's call to accept or tighten):
median generation-throughput regression **< 2 %** and within the OFF-arm
drift band; daemon `VmHWM` increase **< 8 MiB**; `metrics/` growth
**< 15 MB/day** extrapolated. Failing a threshold retunes the flush
cadence and buffer size and the procedure is re-run — it does not result
in reporting the measurement as passed.

**Stated limitation:** N = 20 in a single session bounds the confound
estimate but does not establish it at 24/7 scale. A second, longer
observation (48 h with the layer on, comparing `metrics/` growth against
the §6 projection) is proposed as a follow-up rather than claimed here.

---

## 6. Rotation and retention, with the bytes/day math

### 6.1 Per-category rate and size

Rates are grounded in verified cadences (facts 0.12, 0.24), not guesses.
Record sizes are estimated from the field counts in §2 at ~55 bytes per
populated field including JSON syntax, plus a ~260-byte envelope.

| Cat | Events/day | Basis | Bytes/record | Bytes/day |
|---|---|---|---|---|
| A inference | 2,000 | Generous upper bound: Aigentik's whole current log is 130–672 KB/day (fact 0.24) and includes far more than completions; plus coding-agent + planner traffic | 1,100 | 2.20 MB |
| B gate | 2,000 | **Edge-triggered** (§2.B). Without it: 172,800 evaluations/day at 0.5 s (fact 0.12) | 900 | 1.80 MB |
| C device | 2,880 | 86,400 s ÷ 30 s watchdog tick (fact 0.12) | 450 | 1.30 MB |
| D co-tenancy | 200 | Transitions only; a heavy day is ~100 TUI sessions | 400 | 0.08 MB |
| E task | 400 | ~200 tasks × 2 records (start + finish) | 1,200 | 0.48 MB |
| F extraction | 1,000 | ~500 extractions × 2 (attempt + grounding) | 800 | 0.80 MB |
| G provenance | 20 | Process starts/day across 4 emitters incl. restarts | 2,000 | 0.04 MB |
| meta | 100 | Heartbeats + emit_cost every 5 min per emitter | 500 | 0.05 MB |
| | | | **Total** | **≈ 6.75 MB/day** |

**The contrast that justifies edge-triggering:** naive per-evaluation
gate logging alone would be
`172,800 × 900 B ≈ 155 MB/day` → **56 GB/year**, which on a device with
94 GB free (fact 0.22) is not survivable for a system meant to run 24/7
indefinitely. With edge-triggering the whole layer is **6.75 MB/day**, of
which gate records are 1.8 MB — an ~86× reduction on that category with
**no loss of rate information**, because `repeat_count` sums back to the
exact evaluation count.

### 6.2 Growth projection

- Raw, uncompressed: 6.75 MB/day → **2.46 GB/year**.
- JSONL of this shape (highly repetitive keys) compresses ~10× with gzip.
  Archived: **≈ 0.68 MB/day → 0.25 GB/year**.
- Steady state after the first week: 7 days raw (47 MB) + archives
  (0.25 GB/yr) + `rollups.db` (daily aggregate rows, ~2 KB/day
  → 0.7 MB/yr).
- **Year 1 total ≈ 0.30 GB. Year 5 ≈ 1.3 GB.** Against 94 GB free
  (fact 0.22), that is 0.3 % of free space after five years.

### 6.3 Policy

- **Raw JSONL:** kept uncompressed in `events/<date>/` for **7 days**.
- **Archive:** day directories older than 7 days are `tar` + `gzip`ed
  into `archive/<YYYY-MM>/<YYYY-MM-DD>.tar.gz`. The source directory is
  removed **only after** the archive is written, `fdatasync`ed, and
  successfully re-read and line-counted. A `meta`/`rotation` record logs
  the source byte count, archive byte count, and record count on both
  sides. If the verification read fails, the source is left in place and
  the failure is recorded.
- **Archives are kept indefinitely. There is no deletion code path in the
  layer at all.** `rotate` cannot delete an archive; nothing can, short
  of a human running `rm`. This is the direct implementation of the
  append-only/immutable requirement and the deliberate opposite of
  Aigentik's `pruneOldLogs`. (Confirmation requested, §8 item 8.)
- **Rollups:** daily aggregate rows in `rollups.db`, kept indefinitely,
  rebuildable from raw + archives.
- **Guardrail (not a deletion path):** `codey-metrics status` prints a
  warning when `metrics/` exceeds **2 GiB** — roughly year 8 at the
  projection above, so it should never fire unless the rate assumptions
  are wrong. If it fires, that is a signal the projection was wrong and
  needs re-deriving, which is exactly what it is for.
- **Compression choice:** gzip via Python's stdlib `tarfile`/`gzip`,
  because it adds **no new dependency** and therefore no `install.sh`
  change beyond the `codey-metrics` symlink (rule 11). zstd would give a
  better ratio at the cost of a `pkg install` — offered in §8 item 6.

---

## 7. Phase 3 sub-task breakdown, ordered by risk (lowest first)

Rule-4 flags: any sub-task touching `core/daemon.py`, `core/loader_v2.py`,
`core/inference_hybrid.py`, `core/plannd.py`, or `core/resource_gate.py`
**requires an explicit code-reviewer approval before it can be considered
done**, regardless of diff size. Those are marked **[R4]** and are
deliberately ordered last.

### Where category F sits, and why

**F ships second — immediately after the foundation, ahead of five
lower-risk sub-tasks.**

By pure risk ordering F would rank around 4th: it edits `llama.js`, a
live file handling real customer data. It is nonetheless scheduled
second, because **F is the only category whose data is unrecoverable.**

- A, B, C, D, E measure *the system*. The system will still be here next
  month, and its rates are stationary — instrument it in November and you
  can measure the same phenomena you would have measured in September.
- F measures *events that happen once*. Every extraction attempt that
  occurs before F ships is a permanently missing row in the denominator.
  Worse, §1.4 established that Aigentik's existing 30-day
  `pruneOldLogs` has **already destroyed** the reject-side history older
  than 30 days, so even a partial reconstruction from existing logs has a
  hard 30-day horizon that shrinks by one day every day.
- The specific claim the grant needs — "the grounding check rejects X %
  of extractions, passes Y % verified, and passes Z % unverified" — has
  **no denominator at all** today (fact 0.16). It cannot be
  back-computed from anything.

F's risk is also genuinely contained: two call sites, purely additive,
`isAddressGrounded()` left byte-identical, and a JS file that is not on
any process-lifecycle path.

**Ordering:**

| # | Sub-task | Touches | Risk | R4? |
|---|---|---|---|---|
| **T0** | **Foundation.** `telemetry/` package: schema v1.json, `schema.py`, `envelope.py`, `store.py` (ring buffer + writer thread + JSONL append + kill switch), `provenance.py`, `recorders.py`, plus `tests/test_telemetry_*`. **No call sites touched — nothing imports it yet.** Includes `test_telemetry_no_ccos_imports.py`. | new files only | **None** — dead code until T1 | No |
| **T1** | **Category F (Aigentik) — SHIP FIRST after T0.** `telemetry.mjs` (JS writer, prune interlock, schema copy + hash parity test), `classifyAddressGrounding()`, F emission at `llama.js:554` and `:726`, `deterministic_bypass` emission at the rule sites, `chat()` gains an optional 3rd `meta` param. `isAddressGrounded()` unchanged. | `llama.js` (+2 call sites, +1 pure fn), new `telemetry.mjs` | **Low** — additive, no lifecycle path | No |
| **T2** | **Category G for non-lifecycle emitters.** `run_start` from Core API, Aigentik, and the TUI at process start; `runs/<id>.json`; model-digest cache. Write-once, no decision path observed or touched. | `restoricon_core/api/server` entry, `main.py` TUI entry, `telemetry.mjs` init | **Low** | No |
| **T3** | **Category A at the Core AI proxy.** Emit A from `/api/v1/ai/chat` after `resp_data` is parsed (fact 0.18). This single site captures **every Aigentik local-model completion** server-side, in Python, with full `timings`. High value per unit of risk. | `restoricon_core/api/routes.py` (one block) | **Low** — read of an already-parsed dict; RBAC untouched | Review recommended (API surface) |
| **T4** | **`codey-metrics` CLI + rollups + rotation.** `cli.py`, `rollup.py`, `rotate.py`, the `codey-metrics` entry script, `install.sh` update (fact 0.25). Entirely offline and read-mostly over the store. | new files + `install.sh` | **Low** | No |
| **T5** | **Category A at `core/inference_hybrid.py`.** Capture the full `timings` block, `usage`, `finish_reason`, `id`, `system_fingerprint`; `ttft_ms` at the existing `on_first_token` boundary; emit one record per completion. Also emits the B record for the `wait_and_reserve_context_budget()` wrapper call (outside the lock). | `core/inference_hybrid.py` | **Medium** — inference hot path | **[R4]** |
| **T6** | **Category A + B at `core/plannd.py`.** Same treatment at the planner's own budget call site (`core/plannd.py:562`), `role="planner"`. | `core/plannd.py` | **Medium** | **[R4]** |
| **T7** | **Category E task outcomes.** `task_started`/`task_step`/`task_finished` from `core/task_executor.py`; step/tool/retry/escalation counters surfaced from `core/agent.py`'s loop. `_execute_task()` accepts `task_id`/`task_type`/`needs_planning` as optional keyword-only parameters and emits them when supplied, but no production caller supplies real values yet — both real call sites in `core/daemon.py` pass only a bare prompt string, so this wiring is present but inert until `core/daemon.py` is changed to source them from the `task_queue` row (T8). Does **not** cover the `superseded_by_plan` terminal status at all: that code path (`core/daemon.py:1349-1351`) never calls `_execute_task()`, so no T7 change can reach it — also T8. | `core/task_executor.py`, `core/agent.py` | **Medium-high** — dispatch-adjacent; `agent.py` is the main loop | **[R4]** (flagged by association) |
| **T8** | **Categories B, C, D and daemon-side G at `core/daemon.py`.** Edge-triggered gate records at `_check_dispatch_gate()`; C on the existing 30 s watchdog tick; D transitions and deferral tracking; `run_start`/`counter_reset` at daemon start; `writer_stopped` in the shutdown `finally`. | `core/daemon.py` | **High** — process-lifecycle module, the worst-bug category in this project's history | **[R4]** |
| **T9** | **Category B at `core/loader_v2.py`.** `can_admit()` decision records at the model-load call sites; capture the exact `llama_server_argv` into the run provenance record. Plus the §8-item-7 decision on the `"w"` log truncation, if Ish wants it changed. | `core/loader_v2.py` | **High** — process spawn/lifecycle, and this is where PID/kill handling lives | **[R4]** |

**Sequencing note:** T5–T9 all depend on T0 and are independent of each
other, so if a code-reviewer pass on T8 stalls, T9 does not block behind
it. T1 depends only on T0, which is why F can ship on day two.

**Explicit non-goal for Phase 3:** `core/resource_gate.py` is not edited
by any sub-task. If a sub-task discovers it *must* be edited, that is a
scope change requiring a fresh decision, not an in-flight extension —
it is the single most safety-critical module in the system and every
decision object needed is already returned by its public API.

---

## 8. Ambiguous points — flagged for Ish's decision, not silently defaulted

Each of these has a recommendation, but none should be treated as
settled without an explicit answer.

**1. Category D's detector split is not implementable as specified.**
The spec asks to record "which detector fired (TUI/GUI client/both)".
`is_gui_client_connected()` was **removed on 2026-09-02** and
`is_interactive_session_active()` now delegates unconditionally to the
TUI detector (fact 0.10) — the removal was deliberate, because the old
GUI signal had a fail-open trap that would have deferred all background
dispatch forever.
*Recommendation:* record `detector: "tui"` and
`detector_available: ["tui"]`, keeping the field shape so a future
detector needs no schema bump. **Question:** should the web dashboard's
active sessions become a second interactive detector? That is a genuinely
new signal with a real fail-open hazard, and it is a scope addition, not
a telemetry decision.

**2. There is no preemption to measure.** The spec asks for "for each
preemption, how long background work was suspended and whether task state
survived". Verified (fact 0.11): the gate is a *pre-claim* check; a
refused task is never claimed and in-flight work is never suspended.
*Recommendation:* substitute **deferral** — `deferral_ms` (first refusal
→ eventual dispatch), `deferral_refusal_count`, and
`task_state_preserved` (structurally always `true` today, recorded rather
than assumed so a future real preemption path would show `false`).
**Question:** is deferral the measurement you actually wanted, or is
adding real preemption a separate goal?

**3. Prompt and extracted-value content: hash, or not even that?**
The store is permanent, immutable, exportable, and destined for a grant
package. Aigentik handles real customer names, addresses, phone numbers
and email bodies.
*Recommendation:* **never store content.** Store `prompt_sha256`,
`prompt_chars`, `message_count`, and the role sequence; for grounding,
`value_sha256` and `value_chars`. That preserves "the same prompt
produced these two different results" as a verifiable claim without
storing text.
**Question:** is a SHA-256 of a customer address acceptable to you, or
should even that be dropped in favour of length + field-name only? A
hash of a short, guessable string (a street address) is not a strong
redaction against someone with a candidate list.

**4. The category-G env/config allow-list.** Live env contains
`OPENROUTER_API_KEY`, `UNLIMITEDCLAUDE_API_KEY`,
`CLOUDFLARE_TUNNEL_TOKEN`; `~/Codey-Aigentik/config.json` contains
`core_api.token` (fact 0.21). Append-only means a leak here is not
editable afterwards.
*Recommendation:* the explicit allow-list in §2.G, plus presence-only
booleans for secret-bearing names, and a hard rule that a wholesale
`os.environ` or `config.json` dump is never written.
**Question:** confirm the allow-list contents, and confirm that recording
`{"openrouter_api_key_set": true}` is acceptable.

**5. Cross-repo schema: byte-identical copies, or a configured path?**
Aigentik has no configured path to the Codey-OS tree (verified in
`config.json`).
*Recommendation:* byte-identical copies + `schema_sha256` in every record
+ parity tests on both sides + `codey-metrics schema --verify`. This
survives Aigentik being deployed without Codey-OS present.
*Alternative:* add `paths.codey_os_dir` to Aigentik's config and read the
one canonical file — no drift possible, but a new hard cross-repo
coupling and a new failure mode if the path is wrong.
**Question:** which?

**6. gzip vs zstd for archives.** gzip is stdlib (no `install.sh`
dependency change); zstd compresses this data materially better and
faster but needs `pkg install zstd` and a rule-11 `install.sh` update.
*Recommendation:* gzip — at 0.68 MB/day archived, the ratio difference is
worth well under a gigabyte over five years, which does not justify a new
system dependency.
**Question:** agree?

**7. `~/.codeyOS/llama-server.log` is truncated on every model reload**
(fact 0.9 — `loader_v2.py:731` opens it `"w"`). Every reload destroys the
prior server's `print_timing` history.
*Recommendation:* **do not fix it as part of this work.** The new layer
takes its numbers from the HTTP response, so it does not depend on that
log; changing `"w"` → `"a"` means touching `core/loader_v2.py` (rule 4,
process-spawn code) for a benefit the telemetry layer does not need, and
introduces an unbounded-growth log that would then need its own rotation.
Log it as a `NEW-###` finding instead.
**Question:** accept leaving it, or do you want the historical
`print_timing` output preserved too? It is genuine evidence loss either
way — this is a judgment call about which loss matters more.

**8. "Never delete" is being taken literally.** The design contains no
deletion code path at any retention age. At the §6 projection that is
~1.3 GB after five years on a device with 94 GB free.
*Recommendation:* confirm literal. The alternative — any automatic
deletion — undermines the append-only claim the grant rests on.
**Question:** confirm, and confirm the 7-day raw→archive threshold.

**9. Is `rollups.db` evidence, or a cache?**
*Recommendation:* **a rebuildable derived cache, explicitly not
evidence.** That lets it be dropped and regenerated if it is ever found
inconsistent, without any claim about the dataset being weakened. The
raw JSONL and archives are the evidence.
**Question:** confirm — if a grant reviewer would be shown rollup numbers
directly, they may need to be treated as evidence too, which would mean
`rollups.db` also becomes append-only and never rebuilt in place.

**10. `/proc/uptime` is permission-denied on this device (fact 0.2)** —
a previously undocumented sibling of NEW-108. Device uptime therefore
cannot be recorded and is a permanent honest null.
*Recommendation:* record it as an explicit null with reason
`proc_uptime_permission_denied` so the restriction is visible in the
dataset rather than absent from it, and log a `NEW-###` finding.
**Question:** none — this is a report, but it is listed here because it
was discovered during this design pass and is outside the original brief
(CLAUDE.md rule 8).

---

## 9. Plain-language summary

**What I'm proposing.** Codey-OS already computes almost everything worth
measuring — how fast the model ran, why the resource gate said yes or no,
how hot the phone is, whether a human was at the keyboard — and then
throws essentially all of it away. This adds a thin recording layer that
writes those already-computed facts to one place,
`~/.codeyOS/metrics/`, as plain one-line-per-event JSON files that are
only ever appended to and never edited. Every record says which code
version, which phone, which model file, and which config produced it, and
anything we couldn't measure is written down as "unknown, because X"
rather than quietly left out or filled in with a zero. A new
`codey-metrics` command reads it back on the phone screen or exports a
date range to CSV. It should cost about 7 MB a day, roughly 2 MB of RAM
across all processes, and no measurable slowdown — and there's a
step-by-step procedure here to actually prove that rather than assert it.

Two conflicts from the earlier survey are resolved: the new layer does
**not** touch the CCOS performance database, because that database feeds
the permanently-disabled self-improvement modules and nothing new should
be wired anywhere near them; and Aigentik's 30-day log deletion cannot
reach the new store, because it only ever deletes files named
`aigentik-*.log` inside its own logs folder — plus the new writer
actively refuses to start if it ever finds itself inside that folder.

The Aigentik extraction/grounding piece ships **second**, right after the
plumbing, ahead of five safer pieces. Everything else measures the
system, and the system will still be here next month. That piece measures
events that happen once — and right now we only log the *failures*, so we
literally cannot say what percentage of address extractions the safety
check catches. Every day without it is a day of that number we can never
get back.

**The main risk.** The last two pieces of work touch `core/daemon.py` and
`core/loader_v2.py` — the process start/stop and model-spawn code that
has produced this project's worst bugs, including a fix that passed two
code reviews and still shipped broken. They're deliberately scheduled
last and both require a full code-reviewer pass. The design's answer is to
keep the risky files as untouched as possible: the resource gate itself
gets **zero** edits, nothing is instrumented inside a lock or inside a
per-token loop, and the one measurement that would have been most
tempting to put in the wrong place — the context-budget decision, which
runs while holding a lock every other process waits on — is deliberately
recorded from outside that lock instead, one record per request rather
than one per retry.

**The second risk, worth knowing about.** The dispatch gate is evaluated
twice a second. Recording every evaluation would be about 155 MB a day
and would tell us nothing we don't learn from far fewer records. The
design only writes a record when the answer *changes*, plus a once-a-
minute heartbeat carrying a count of what it skipped. That's an ~86×
reduction with no loss of information — but it does mean the raw file is
not a literal transcript of every call, and anyone reading the data has
to sum the `repeat_count` field to recover true call counts. That's
documented in the schema, but it's the one place where the store is
cleverer than "write down everything", and cleverness is where mistakes
live.

**Ten things I want your call on before any code is written** are in §8 —
the most important being what we do about storing hashes of customer
addresses (§8 item 3), which environment variables are allowed anywhere
near a permanent exportable store given that API keys sit right next to
them (§8 item 4), and confirming that "never delete anything, ever" is
meant literally (§8 item 8).
