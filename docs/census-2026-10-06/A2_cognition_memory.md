# CENSUS TASK A2 — Cognition, Memory, Retrieval, Reflection, Goals, Self-Improvement

Read-only static census. Date: 2026-10-06. Branch inspected: `main` (plus
`codey-os-dev-v2` diff for §e). No service started, no model loaded, no
production DB opened.

**Entry points used for reachability tracing:** `codey-start` (22 lines →
`lib/service_manager.sh::start_all_services` → `codeyOS`), `codeyOS` (shells
out to generated `python3` scripts that import `main.py`), `main.py`,
`core/agent.py`, `core/daemon.py`.

**Mechanical test applied:** a module is IMPLEMENTED/live only if a concrete
import chain exists from one of those entry points. `ccos/demo_*.py` and
`*/tests/` are NOT entry points.

---

## (a) Memory tier table

`core/memory_v2.py:545` `class Memory` composes five tiers
(`core/memory_v2.py:573-578`). Module-level singleton `memory` at
`core/memory_v2.py:743`, imported live from `main.py:1080`, `core/agent.py:1277`,
`core/context.py:11`, `core/daemon.py:930`, `core/task_executor.py:365`,
`prompts/layered_prompt.py:260`.

| # | Tier | Class | Written? | Read back into a prompt? | Status |
|---|------|-------|----------|--------------------------|--------|
| 1 | Working Memory | `memory_v2.py:90` | **Yes, live — but conditionally.** `core/context.py:91` `load_file()` → `_mem.load_file()`; auto-invoked by `core/context.py::auto_load_from_prompt` at `core/agent.py:1642`, **gated at `core/agent.py:1641` by `if used < total * 0.5`** (`get_context_usage` at `:1640`) — i.e. auto-loading silently stops once the prompt already occupies half of `n_ctx`. Explicit `load_file`/`load_glob`/`load_directory` paths are ungated. | **Yes, live.** `prompts/layered_prompt.py:355` `p.add("files", _get_file_block(...), priority=4)` → `layered_prompt.py:207-209` → `core/context.py:176` → `memory_v2.py:593` `build_file_block()` → `memory_v2.py:199` `select_for_context()` (relevance-scored, 6000-char budget). Reaches the draft system prompt. | **IMPLEMENTED** |
| 2 | Project Memory | `memory_v2.py:241` | **Yes, but only by the daemon.** Only writers: `core/daemon.py:937` and `:944` (`add_to_project` for CODEY.md and config, `is_protected=True`). | **No.** Only reader outside the class is `main.py:1147` `_mem.project.get_protected_files()` — a status/TUI display. `ProjectMemory` stores only an md5 hash, not content (`memory_v2.py:249-255`); `get()` at `:257` returns the *path*, not content — it cannot feed a prompt. **The "Project Memory" block in the prompt (`layered_prompt.py:173-190`) comes from `core/codeymd.read_codeymd()`, a completely separate path that never touches this tier.** | **PARTIAL** (write-only; duplicated by `core/codeymd.py`) |
| 3 | Long-term Memory (embeddings) | `memory_v2.py:280` | **No.** `store_in_longterm` (`memory_v2.py:663`) and `LongTermMemory.store_file` (`:303`) have **zero callers** outside the class. Searched: `/usr/bin/grep -rn "store_in_longterm\|\.longterm" --include=*.py .` → only `memory_v2.py` itself. | **No.** `Memory.search()` (`memory_v2.py:684`) has zero callers (`grep -rn "_mem.search("` → nothing). | **DORMANT** — and a **dead parallel implementation**: its backing store `core/embeddings.get_embedding_store/get_embedding_model` is called from exactly one place, `memory_v2.py:299-301`. The RAG that *is* live uses an entirely separate numpy/json index in `tools/kb_semantic.py` (`vectors.npy` / `mapping.json` / `vectors.meta.json`, `kb_semantic.py:428-449`). Two unconnected embedding retrieval stacks. |
| 4 | Episodic Memory | `memory_v2.py:363` | **Partially, live.** `Memory.tick()` (`memory_v2.py:649`) calls `self.episodic.log("tick", ...)` at `:652`, and `tick()` is called live at `core/agent.py:1679` — so a `"tick"` row is written every turn. The *meaningful* writer, `log_observation` (`memory_v2.py:674`), has exactly one caller: `core/agent.py:1278`, inside `_run_symbolic_pipeline` — **gated off by default** (see tier 5). Backing store is `core.state.get_state_store()` (`memory_v2.py:375`). | **No.** Only reader is `main.py:1165` `_mem.episodic.get_recent(10)` — TUI display. No episodic content reaches any prompt. | **PARTIAL** (writes content-free ticks; observation writes gated off; never read into behavior) |
| 5 | Symbolic Memory | `memory_v2.py:426` | **Gated off by default.** `SymbolicMemory.observe` is reached only via `Memory.log_observation` (`memory_v2.py:674-678`) ← `core/agent.py:1278`, and via `core/agent.py:1256-1267` `graph.execute_batch(ops)`. Both live inside `_run_symbolic_pipeline`, whose only call site is `core/agent.py:1328-1332`, guarded by `core/agent.py:1327`: `_symbolic_enabled = os.environ.get("CODEY_SYMBOLIC", "0") == "1"` — **default off**. | **Read path exists and is live, but reads an empty graph.** `prompts/layered_prompt.py:257-264` `_get_symbolic_graph_block()` → `_mem.to_natural_language()`, added to the prompt at `layered_prompt.py:356`; and `core/retrieval.py:140-158` queries the graph *first* in `retrieve()`. Both guard on `_mem.symbolic._available`, which is True whenever `core.symbolic_graph` imports (`memory_v2.py:443-448`; pure stdlib `sqlite3` + `utils.config`, `symbolic_graph.py:29-38`) — so the guard passes, but with `CODEY_SYMBOLIC=0` nothing ever writes concepts, so `to_natural_language()` returns `"No concepts in graph."`, which `layered_prompt.py:263` explicitly filters out. | **PARTIAL** (read-back wired end-to-end; write side gated off by default ⇒ no-op in production) |

### Session summary (a sixth, undocumented store)
`Memory._summary` (`memory_v2.py:580`) has **two** writers and neither runs:
- `append_to_summary` (`memory_v2.py:606`) — **zero callers anywhere** (searched
  `grep -rn "append_to_summary" --include=*.py .` → only the definition).
- `compress_summary` (`memory_v2.py:615`) — **zero production callers**; removed
  from the agent loop with an explanatory comment at `core/agent.py:1811-1813`
  ("it calls infer() on the same 7B model … causing a single-slot collision").

Its only reader is `main.py:1128-1129`, a TUI display. So `get_summary()` always
returns `""` in production. **Status: DORMANT.** History compression is actually
done by a different module, `core/summarizer.py` (`should_summarize` /
`summarize_history`, called at `core/agent.py:1809-1810`) — another duplication.

### `ccos/core/memory/ccos_memory.py`
A second, structurally unrelated memory system: `StructuredDB` (skills,
workflows, configs, preferences, performance — `ccos_memory.py:37-86`),
`EventLog` (`:224`), `VectorStore` (`:283`), unified as `CCOSMemory` (`:342`)
with `store_task_result` (`:352`) and `get_similar_tasks` (`:378`).

**Reachability: DORMANT.** All five callers of `get_ccos_memory()` are inside the
dormant CCOS cluster (`goal_engine.py:121`, `auto_improvement_loop.py:54`,
`lifecycle_manager.py:105`, `skill_recombiner.py:513`) or demos
(`demo_goal_engine.py:44`, `demo_skill_recombiner.py:44`). Nothing in `core/`,
`tools/`, `utils/`, `main.py`, or `restoricon_core/` imports it (see §c
enumerated grep). Nothing it stores reaches any prompt.

DB state (`ccos/data/ccos_memory.db`, read via `mode=ro`): it contains
**`cap_metrics` = 454 rows, `cap_versions` = 2, `cap_snapshots` = 3** — i.e. the
`performance_tracker` schema (`ccos/core/performance_tracker.py:20` points at the
same file), **not** the `ccos_memory.py` tables. The `skills` / `workflows` /
`configs` / `preferences` / `performance` / `events` tables defined at
`ccos_memory.py:37-249` **do not exist in the DB at all** — confirming
`CCOSMemory` has never run against it.

---

## (b) RAG & context construction

### Context assembly — the one live path
`core/agent.py:1800-1802` builds the system prompt via
`prompts/layered_prompt.build_recursive_prompt(user_message, phase="draft",
plan_rag_block=..., lightweight=is_qa)`. `core/agent.py:944-951`
`build_system_prompt()` is a thin alias to the same function.

`prompts/layered_prompt.py:84-141` `class LayeredPrompt`: greedy inclusion by
priority within a char budget; `required` layers bypass the budget
(`layered_prompt.py:118`). `_build_draft_prompt` (`layered_prompt.py:270`) sets
`LayeredPrompt(budget_chars=20000)` at `:306` and assembles:

| Layer | Priority | Source | file:line |
|---|---|---|---|
| `identity` | 0, **required** | `prompts/system_prompt.get_system_prompt()` / `get_qa_system_prompt()` | `layered_prompt.py:307-309` |
| `capabilities` | 1 (keyword-gated) | `system_prompt.CAPABILITIES_PROMPT` | `layered_prompt.py:312-315` |
| `notes` | 1 | `core/notes.get_notes_block()` | `layered_prompt.py:144-151, 317` |
| `prefs` | 1 | `core/learning.get_learning_manager().get_all_preferences()` | `layered_prompt.py:154-170, 318` |
| `project` | 2 | `core/codeymd.read_codeymd()`, else `core/project.get_project_summary()` | `layered_prompt.py:173-190, 319` |
| `repo_map` | 3 | `core/project.get_repo_map()` | `layered_prompt.py:194-201, 321` |
| `retrieval` | 3 | pre-fetched `plan_rag_block`, else `core/retrieval.retrieve()` | `layered_prompt.py:326-336` |
| `skills` | 3 | `core/skills.load_relevant_skills()` | `layered_prompt.py:339-347` |
| `files` | 4 | Working Memory (tier 1) | `layered_prompt.py:355` |
| `symbolic_graph` | 3 | Symbolic Memory (tier 5) | `layered_prompt.py:356` |

`lightweight=True` (QA/smalltalk, classified at `core/agent.py:1770-1788`) skips
repo_map, retrieval, skills, files and symbolic_graph entirely
(`layered_prompt.py:320`). A draft-prompt cache keyed on time + files-hash +
lightweight flag exists at `layered_prompt.py:218-255`.

### RAG pipeline — wired but with no corpus
`core/retrieval.py:retrieve()` is called from three live sites:
`prompts/layered_prompt.py:332`, `main.py:686` (pre-fetch once per plan, passed
down as `plan_rag_block`), `core/orchestrator.py:400` and `:653` (per-subtask),
`core/recursive.py:550` (targeted `NEED_DOCS` gap-filling).

Pipeline (`core/retrieval.py:131-200`): `extract_query` (strips ~40 filler words,
`retrieval.py:30+`) → symbolic-graph query first (`:140-158`) → KB
`semantic_search` if `has_index()` else `keyword_fallback` (`:161-170`) → filter
on `semantic_threshold` (default 0.3) and a `relevance_gate` (default 0.72) that
drops *all* results if the best cosine is below it (`:181-188`) → format into a
`## Reference Material` block within `budget_chars` (default 2400).

**Verified on-device, statically:** the knowledge base does not exist.
- `tools/kb_scraper.py:23` `KB_ROOT = $CODEY_DIR/knowledge` →
  `/data/data/com.termux/files/home/Codey-OS/knowledge` — **does not exist**.
- `tools.kb_semantic.has_index()` → **False** (evaluated directly; no model load).

So `retrieve()` returns `""` on every call today. **Status: PARTIAL** — the
pipeline is IMPLEMENTED and reachable; the corpus is MISSING.

**No programmatic KB ingestion path.** `tools/kb_scraper.index_file` /
`index_directory` and `tools/kb_semantic.build_semantic_index` have **zero Python
callers** (searched `grep -rn "kb_scraper\|build_semantic_index\|index_directory"
--include=*.py .`). Neither file has a `__main__` block. The only invoker is the
manual one-shot shell script `tools/setup_skills.sh:103,126,142-144,181`, which
has evidently never been run here. `core/skills.load_relevant_skills`
(`core/skills.py:28`) searches the same absent KB, so the `skills` layer is also
empty in practice.

### Context-ceiling / slot-reservation — three distinct mechanisms
These are frequently conflated; only (c) is the NEW-145/149/155 lineage.

**(a) Char budget on the prompt.** `LayeredPrompt(budget_chars=20000)`
(`layered_prompt.py:306`); critique prompt uses 8000 (`:458`). Greedy, priority
ordered, `required` layers exempt (`:118`). Plus `_safe_truncate_draft`
(`layered_prompt.py:378-429`) which never cuts inside a `<tool>` block —
`_TOOL_BLOCK_RE` / `_UNTERMINATED_TOOL_RE` (`:375-...`), the second pattern
specifically to catch stop-sequence-elided closing tags.

**(b) Token-level history compression.** `core/tokens.get_context_usage`
(`tokens.py:45`), used at `core/agent.py:1640` (gates `auto_load_from_prompt` to
when usage < 50% of n_ctx) and `core/agent.py:1867`.
`core/summarizer.should_summarize` (`summarizer.py:162`) →
`summarize_history()`, called at `core/agent.py:1809-1810`. `memory_v2`'s own
`get_ctx_total()` (`memory_v2.py:50`) reads `MODEL_CONFIG["n_ctx"]` live — the
NEW-102 import-order fix; its docstring at `:47` states no caller reads it today
(confirmed).

**(c) Resource-gate slot reservation.** `core/resource_gate.py:3336+`
`reserve_slot()` / `:3639` `release_slot()`. **The single production call site
repo-wide is `core/loader_v2.py:1450`** — verified with a repo-wide
`grep -rn "reserve_slot(" --include=*.py .` excluding `core/resource_gate.py`
itself and comment-only lines; every other hit is in `tests/` (chiefly
`tests/test_resource_gate.py`, `tests/test_loader_resource_gate.py`,
`tests/test_loader_v2_telemetry.py`) or `.live_verify_scratch/`:
```python
decision, slot_id = rg.reserve_slot(spec, port=PRIMARY_SERVER_PORT, meminfo=gate_meminfo)
```
The `port=` kwarg present here is the NEW-259 fix (its absence had made the
mechanism a permanent no-op). `release_slot` call sites: `core/loader_v2.py:501,
1533, 1602, 1731`, `core/embed_server.py:279`. `core/embed_server.py:196-201`
documents a deliberate bypass — the embedding server never competes for a slot.
Note `core/resource_gate.py:1076` carries a stale comment claiming "nothing in
this codebase calls reserve_slot()"; `loader_v2.py:1450` contradicts it. **Logged
as a finding candidate in §g.**

---

## (c) Planner / orchestrator duplication — canonical recommendation

There are **two complete, mutually unreferenced stacks**.

### The decisive evidence
Enumerated grep for every CCOS import from the live tree:
```
/usr/bin/grep -rn "^from ccos\|^import ccos\|from ccos\.\|import ccos\." \
  --include=*.py main.py core/ tools/ utils/ restoricon_core/ prompts/
```
**Complete result — 9 hits, 2 distinct modules:**
- `ccos.core.plugin_manager` — `main.py:561`, `core/agent.py:316`,
  `core/task_executor.py:355`, `core/dashboard_data.py:35`,
  `restoricon_core/api/routes.py:533`
- `ccos.core.task_blackboard` — `core/peer_cli.py:434, 467, 487, 507`

**Transitive closure** (second hop, searched with no `head` truncation:
`grep -rn "from ccos\|import ccos" --include=*.py ccos/core/plugin_manager.py
ccos/core/capability_registry.py ccos/core/task_blackboard.py
ccos/core/manifest_schema_v2.py ccos/core/task_context.py` → 4 hits):
`plugin_manager.py:33` → `capability_registry`, `:39` → `manifest_schema_v2`,
`:40` → `task_context`; `task_blackboard.py:17` → `task_context`.
`capability_registry`, `manifest_schema_v2` and `task_context` import no further
CCOS modules, so the closure terminates.

**The live CCOS surface is exactly five modules:** `plugin_manager`,
`capability_registry`, `manifest_schema_v2`, `task_context`, `task_blackboard`.
Notably **absent** from the closure: `sandbox`, `tool_router`, `domain_router`,
`agent_orchestrator`, `planner`. **Nothing else in CCOS is reachable from any
entry point.**

### Stack 1 — `core/` (CANONICAL, live)
| Module | Role | Live call path |
|---|---|---|
| `core/planner_service.py` (132 ln) | daemon plan-request helper | `main.py:517-518` → `_request_daemon_plan` |
| `core/planner_client.py` (50 ln) | async plan RPC | `core/daemon.py:251, 1837` → `send_plan_request_async` → `core.plannd.get_plan` (`planner_client.py:42`) |
| `core/plannd.py` (1090 ln) | the actual planner; runs **inside the daemon process** (`plannd.py:81-82`) | reached via the two above |
| `core/orchestrator.py` (762 ln) | complex-task decomposition into a `TaskQueue` | `core/agent.py:1646` → `is_complex`, `plan_tasks`, `run_queue` (invoked `agent.py:1648-1664`) |
| `core/planner.py` (71 ln) | interactive show-and-confirm plan | `core/agent.py:1669` — **only under `use_plan=True`** |
| `core/planner_v2.py` (472 ln) | native task queue w/ dependencies, retry, background scheduling (`planner_v2.py:1-9`) | `core/daemon.py:887`, `core/observability.py:77, 90` → `get_planner` |
| `core/recursive.py` (598 ln) | draft → critique → refine self-refinement | `core/agent.py:1884` → `classify_breadth_need`, …; `core/orchestrator.py:431` → `recursive_infer`; also wrapped as a CCOS capability at `ccos/plugins/coding/agent/agent.py:180, 215` |

Live scoring/tiering: `main.py:648` imports `_score_message`, `is_complex` from
`core/orchestrator`; `main.py:660-671` picks a planning tier; `main.py:671`
`_try_daemon_plan`.

**Note an internal duplication inside stack 1:** `core/planner.py`,
`core/planner_v2.py`, `core/plannd.py`, `core/planner_service.py`,
`core/planner_client.py` and `core/orchestrator.py` are six modules for
planning, all reachable, with overlapping responsibilities (`planner_v2` and
`orchestrator` both maintain task queues).

### Stack 2 — `ccos/` (DORMANT)
`ccos/core/planner.py` (455 ln) and `ccos/core/agent_orchestrator.py` (1193 ln),
with `domain_router`, `tool_router`, `capability_registry`, `performance_tracker`,
`lifecycle_manager`.

Internally coherent and mutually wired: `agent_orchestrator.py:967, 1053` import
`ccos.core.planner.get_planner`; `agent_orchestrator.py:1135-1137` bridges an
`ExecutionPlan` to a `ccos.core.planner.Plan`; `ccos/core/planner.py:322-323`
calls back into `get_agent_orchestrator()`; `agent_orchestrator.py:26` →
`domain_router`, `:25` → `capability_registry`, `:27, 193, 438, 529` →
`performance_tracker`; `planner.py:24, 28` → `domain_router`, `tool_router`.

**Every external caller is a demo or a test:**
`ccos/demo_agent_orchestrator.py:23, 38`, `ccos/demo_project_engine.py:26, 41`,
`ccos/demo_goal_engine.py:156`, `ccos/core/lifecycle_manager.py:19` (itself
dormant — its only importers are `demo_goal_engine.py:30`,
`demo_improvement_loop.py:25`, `demo_skill_recombiner.py:31`,
`ccos/tests/test_improvement_loop.py:27`),
`ccos/tests/test_agent_orchestrator_execution.py`, `ccos/tests/test_multi_domain.py`.

`ccos/core/project_engine.py` — zero callers of any kind outside demos.
`ccos/core/telemetry_engine.py` (724 ln) — **zero callers whatsoever** outside
`ccos/demo_telemetry.py:25` and `ccos/tests/test_telemetry.py`; its
`get_insights_for_goal_engine()` (`:550`) is never called.

### Recommendation
**`core/` is canonical, on reachability grounds alone** — it is the only stack any
entry point reaches. The `ccos/` planner/orchestrator stack should be treated as
unintegrated prototype code: either wire it behind the OS shell deliberately, or
move it out of the active tree. Documenting it as "the OS shell that discovers,
routes and monitors capabilities" overstates the current state: the only part of
CCOS actually doing that job in production is `plugin_manager` +
`capability_registry` (+ `task_blackboard` for peer delegation).

Secondary recommendation: consolidate the six-module planner sprawl *within*
`core/`; `core/planner.py` (71 ln, `use_plan`-only) and `core/planner_v2.py` are
the weakest-justified of the set.

---

## (d) Reflection & self-improvement — reachability + gating

### The gating mechanism
`ccos/core/self_improve.py` (24 ln) — three-valued master switch:
`mode()` reads `CODEY_SELF_IMPROVE` ∈ {`off`(default) | `shadow` | `on`},
unknown → `off` (`self_improve.py:12-14`); `enabled()` = not off (`:18`);
`may_deploy()` = `on` only (`:22`).

Guard sites (all lazy, in-function imports):

| Module | file:line | Guard | Effect when off |
|---|---|---|---|
| `goal_engine.analyze_and_generate` | `goal_engine.py:133-135` | `if not _si.enabled(): return []` | no goals generated |
| `goal_engine.inject_into_planner` | `goal_engine.py:610-612` | `if not _si.may_deploy(): return None` | goals never reach a planner even in `shadow` |
| `capability_optimizer.optimize` | `capability_optimizer.py:451-453` | `if not _si.enabled(): return None` | inert |
| `capability_optimizer` (deploy) | `capability_optimizer.py:379-382` | requires a `gate_decision` with `promote=True`, else returns a failed `OptimizationResult` | cannot deploy |
| `skill_recombiner.analyze_and_generate` | `skill_recombiner.py:526-528` | `if not _si.enabled(): return []` | inert |
| `skill_recombiner` (register) | `skill_recombiner.py:607-610` | `if not _si.may_deploy(): "Shadow mode: generated and sandbox-tested, not registered"` | never registered |
| `auto_improvement_loop` | `auto_improvement_loop.py:116-118` | `if self._auto_optimize and capability_used and _si.enabled()` | no optimization triggered |

### Promotion gate — real, and it defaults to refusing
`bench/gate.py:14` `GateDecision(promote, reasons, stats)`; `:23` `decide(base_rows,
cand_rows, **overrides)`; `:43-45` `no_evaluator()` returns
`GateDecision(False, ["no evaluator exists for this target; refusing to promote"])`.

`ccos/core/capability_optimizer.py:478` imports `from bench.gate import
no_evaluator` — so the optimizer's *own* default verdict is refusal.
`capability_optimizer.py:345` documents the contract: an approving
`bench.gate.GateDecision` **and** `CODEY_SELF_IMPROVE="on"`.

**But no production code ever constructs an approving decision.** The only caller
passing `gate_decision=` is `ccos/tests/test_improvement_loop.py:240`. The
`bench/` CLI entry is `python -m bench.promote` (`bench/promote.py:1`), an
operator-run tool, referenced only from `core/finetune_prep.py:601, 784` as
instructional text in generated output. Statistical machinery is real:
`bench/stats.mcnemar_exact`, and `tests/test_promotion_gate.py:58-65` asserts a
false-approval rate ≤ 5% over 200 random trials.

### Per-module reachability

| Module | LOC | Reachable from an entry point? | Status |
|---|---|---|---|
| `ccos/core/reflection_engine.py` | 255 | **No.** `get_reflection_engine()` callers: `auto_improvement_loop.py:22, 50`, `goal_engine.py:32, 122` (both dormant), `demo_goal_engine.py:45`, `ccos/tests/*`. `.reflect(` call sites: `auto_improvement_loop.py:82`, `demo_goal_engine.py:94`, `test_ccos.py:242` — no others. | **DORMANT** |
| `ccos/core/goal_engine.py` | 644 | **No.** Importers: `telemetry_engine.py` (itself dormant), `demo_*`, `tests/*`. | **DORMANT** (+ gated) |
| `ccos/core/auto_improvement_loop.py` | 271 | **No.** Importers: `lifecycle_manager.py` (dormant), `demo_improvement_loop.py`, `ccos/tests/test_improvement_loop.py`, `tests/test_promotion_gate.py`. | **DORMANT** (+ gated) |
| `ccos/core/capability_optimizer.py` | 497 | **No.** Importers: `auto_improvement_loop.py`, `demo_*`, tests. | **DORMANT** (+ gated + bench gate) |
| `ccos/core/skill_recombiner.py` | 740 | **No.** Importers: `goal_engine.py`, `demo_*`, tests. | **DORMANT** (+ gated) |
| `ccos/core/performance_tracker.py` | 328 | **No.** All importers (`agent_orchestrator`, `auto_improvement_loop`, `capability_optimizer`, `goal_engine`, `lifecycle_manager`) are themselves dormant. | **DORMANT** — yet its DB tables hold 454 `cap_metrics` rows (see §h) |
| `ccos/core/lifecycle_manager.py` | — | **No.** Only demos + `test_improvement_loop.py`. | **DORMANT** |
| `core/recursive.py` | 598 | **Yes.** `core/agent.py:1884`, `core/orchestrator.py:431`, `ccos/plugins/coding/agent/agent.py:180, 215`. | **IMPLEMENTED** |

### The crucial distinction: this dormancy is *designed*, not accidental
`tests/test_promotion_gate.py:91-105` `test_no_runtime_core_imports_self_improvement`
walks every `.py` under `core/`, `tools/`, `utils/` and **asserts that none of
them import `goal_engine|auto_improvement_loop|capability_optimizer|skill_recombiner`**.
`tests/test_promotion_gate.py:79-89` `test_modules_are_inert_when_off` asserts
each returns `None`/`[]` with the env var unset.

So the CCOS self-improvement cluster is deliberately quarantined by an enforced
test invariant, exactly per CLAUDE.md rule 1's kill-switch intent. This is the
right call to report as *correct current state*, not as a defect. What is *not*
yet built is the bridge: there is no production code path that would run these
behind the gate even with `CODEY_SELF_IMPROVE=on`, because nothing reachable
imports them at all. Flipping the env var today changes nothing.

`core/recursive.py` is the one self-improvement mechanism that *is* live, and it
is per-turn self-refinement (draft→critique→refine), not weight- or
capability-level learning — it is not gated by `CODEY_SELF_IMPROVE` and does not
need to be.

---

## (e) Trajectory store — `main` vs `codey-os-dev-v2`

### `main` (`core/trajectory.py`, 223 ln)
- **Default off:** `trajectory.py:42-43` `enabled()` = `CODEY_TRAJECTORY == "1"`.
- **DB path:** `trajectory.py:46-51` — `$CODEY_TRAJECTORY_DB` or
  `CODEY_STATE_DIR/trajectories.db`.
- **Schema** (`trajectory.py:28-39`): `episodes(id, ts, tag, prompt, final,
  n_tools, secs, crashed, verifier, passed)`, `tool_calls(episode_id, seq, name,
  args, result, is_error, secs)`, `teacher_traces(id, ts, peer, task, output,
  verifier, passed)`, + indexes `ix_ep_tag`, `ix_tc_ep`.
- **Reachable:** yes. `core/agent.py:2468-2476` applies
  `instrument_run_agent` / `instrument_execute_tool` as decorators at import
  time. Only the outermost `run_agent` on a thread opens an episode
  (`trajectory.py:174-176`, thread-local `_local.ep`). `core/agent.py:181` →
  `record_teacher_trace`. `bench/runner.py` and `restoricon_core/api/routes.py`
  also reference it.
- **Labelling discipline is sound:** `trajectory.py:4-6` — labels come *only*
  from external verifiers via `label_episode` (`:84`) / `label_tag` (`:97`) /
  `label_teacher` (`:155`); the agent's self-assessment is never stored as a
  label. `verified_episodes()` (`:112`) returns only externally-verdicted rows,
  and `:114-115` refuses to create the DB on read.
- **Fail-open:** every hook swallows exceptions (`:195-198`, `:220-222`,
  `:245-246`) so a broken store cannot change agent behavior.

**`main` is NOT full-fidelity.** `core/trajectory.py:24-25`:
```python
_MAX_ARGS = 2000
_MAX_RESULT = 1000
```
and `_trunc` (`:62-64`) hard-truncates. Episode prompt → 4000 chars
(`:203`), final → 2000 chars (`:212`). **This bounds any fine-tune or eval claim
built on the current store** — tool results longer than 1000 chars are silently
cut mid-content.

**Live DB state** (`~/.codeyOS/trajectories.db`, 28 KB, mtime 2026-10-06 04:11,
read via `mode=ro`): `episodes` = **5**, `tool_calls` = **14**,
`teacher_traces` = **0**. Essentially unpopulated — consistent with
default-off.

**Status: IMPLEMENTED but truncating; effectively unpopulated.**

### `codey-os-dev-v2` (2 commits ahead, NOT merged)
`git log --oneline main..codey-os-dev-v2`:
```
97ad62d S0.1: full-fidelity trajectories, export hygiene, bench grade() fix
8d1c37e Stage 0 kickoff: commit handoff + approved execution plan (docs only)
```
`git diff --stat main...codey-os-dev-v2` — 13 files, +1264/−21. Code changes:
`bench/verify.py` (+5/−?), `core/export_hygiene.py` (**new, 155 ln**),
`core/finetune_prep.py` (+47), `core/trajectory.py` (+42/−?), plus
`tests/test_export_hygiene.py` (321 ln), `tests/test_trajectory.py` (+98),
`tests/test_bench_harness.py` (+34), and docs/ledgers.

The `core/trajectory.py` diff replaces truncation with budgeted full fidelity:
- `_MAX_ARGS`/`_MAX_RESULT` → `_MAX_FIELD_CHARS = 1_000_000`,
  `_MAX_EPISODE_CHARS = 8_000_000`, `LEGACY_TRUNC_MARKER`,
  `OVERSIZE_MARKER_PREFIX = "[[codey-trajectory:omitted-oversize"`.
- New `_bounded(x)` — a field over 1M chars is replaced *entirely* by a marker
  (not silently cut).
- New `_budgeted(ep, x)` — per-episode 8M char budget; once blown, this and all
  later fields become the marker and `ep["blown"]` is set, so the episode is
  excluded at export and RAM stops growing.
- `instrument_run_agent` / `instrument_execute_tool` switched from `_trunc` to
  `_budgeted`.
- Docstring rewritten: secrets are no longer claimed to be scrubbed at record
  time — scrubbing moves to export (`core/export_hygiene.py` drops examples
  containing secrets).

**Architectural significance:** the design moves from *lossy-at-record* to
*full-at-record + hygiene-at-export*. That is the correct ordering for a
trajectory store intended to feed fine-tuning, and it is the single most
consequential unmerged change in scope for this census. `main` cannot support a
credible distillation/eval pipeline while it truncates tool results at 1000
chars.

---

## (f) DORMANT findings (consolidated)

Each line states the search performed. All searches used full binary paths
(`/data/data/com.termux/files/usr/bin/grep`) per the Termux constraint.

1. **Entire CCOS cognition cluster.** `ccos/core/planner.py`,
   `agent_orchestrator.py`, `domain_router.py`, `tool_router.py`,
   `lifecycle_manager.py`, `goal_engine.py`, `reflection_engine.py`,
   `telemetry_engine.py`, `auto_improvement_loop.py`, `capability_optimizer.py`,
   `skill_recombiner.py`, `performance_tracker.py`, `project_engine.py`,
   `memory/ccos_memory.py` — a closed, internally-coherent graph whose only
   external callers are `ccos/demo_*.py` and `ccos/tests/`.
   *Searched:* `grep -rn "^from ccos\|^import ccos\|from ccos\.\|import ccos\."
   --include=*.py main.py core/ tools/ utils/ restoricon_core/ prompts/ bench/` → 9
   hits, only `ccos.core.plugin_manager` and `ccos.core.task_blackboard` directly;
   second hop adds only `capability_registry`, `manifest_schema_v2`,
   `task_context` (closure terminates there — see §c). ≈ 6,500 LOC unreached.
2. **`ccos/core/telemetry_engine.py` (724 ln) — zero callers of any kind** except
   `demo_telemetry.py:25` and `ccos/tests/test_telemetry.py`. Not even the
   dormant cluster imports it. *Searched:* `grep -rn
   "TelemetryEngine\|telemetry_engine" --include=*.py --include=*.json .`
3. **`ccos/core/project_engine.py`** — zero callers. *Searched:* `grep -rn
   "project_engine import\|project_engine\." --include=*.py .`
4. **Memory tier 3 (`LongTermMemory`) + `core/embeddings.py`'s store/model.** Zero
   write callers, zero read callers. *Searched:* `grep -rn
   "store_in_longterm\|\.longterm\|_mem.search(\|get_embedding_store\|get_embedding_model"
   --include=*.py .` → only `memory_v2.py:299-301`. A dead parallel
   implementation of retrieval that already exists in `tools/kb_semantic.py`.
5. **`Memory._summary` / `append_to_summary` / `compress_summary`** — no
   production writer; superseded by `core/summarizer.py`. *Searched:* `grep -rn
   "append_to_summary\|compress_summary" --include=*.py .`
6. **`tools/kb_scraper.index_file` / `index_directory`,
   `tools/kb_semantic.build_semantic_index`** — no Python caller, no `__main__`
   block; only `tools/setup_skills.sh`. *Searched:* `grep -rn
   "kb_scraper\|build_semantic_index\|index_directory\|index_file"
   --include=*.py .` plus `grep -n "__main__"` on both files.
7. **Symbolic pipeline write side** — `_run_symbolic_pipeline`
   (`core/agent.py:1210`) is gated by `CODEY_SYMBOLIC` (default `"0"`,
   `core/agent.py:1327`). Consequently tier 5 writes and the only meaningful
   tier 4 writer (`log_observation`) never fire in production. Dormant *by
   configuration*, not by missing caller — `core/symbolic_graph.py` (691 ln) is
   fully implemented and one env var from being live.
8. **Trajectory labelling API** — `label_episode` / `label_tag` /
   `label_teacher` / `verified_episodes` / `verified_teacher_traces` have no
   production caller; they are invoked by `bench/` tooling and tests only.
   Consistent with `teacher_traces` = 0 rows.

---

## (g) TODO / stub inventory

A `grep -rn "TODO\|FIXME\|NotImplementedError\|placeholder\|stub\|XXX:"` across
all in-scope files (`core/memory_v2.py`, `core/symbolic_graph.py`,
`core/recursive.py`, `core/orchestrator.py`, `core/plannd.py`, `core/planner*.py`,
`prompts/`, `tools/kb_semantic.py`, `tools/kb_scraper.py`, `ccos/core/`) returned
**no genuine unfinished-work markers.** Full result set:

| Hit | Verdict |
|---|---|
| `prompts/critique_prompts.py:28, 48`; `prompts/system_prompt.py:301, 303, 313` | Not TODOs — prompt *instructions* telling the model not to emit stubs. |
| `tools/kb_semantic.py:409` `all_vecs.append([0.0] * dim)  # zero vector placeholder` | Intentional: keeps row alignment for chunks whose embedding failed; `:458-486` `reembed_failed()` repairs them. Not unfinished. |
| `ccos/core/device_bridge.py:200` `"""Register default mock/stub implementations for all actions."""` | Real stub layer — but `device_bridge` is outside A2 scope (device limb); flag for the device/limb census task. |

This is unusually clean for a codebase of this size. The gap between intent and
reality here is **not** marked by TODOs — it is expressed as unreferenced
modules (§f), which is why reachability tracing rather than marker-grepping was
the load-bearing method for this task.

### Incidental findings outside A2 scope (per CLAUDE.md rule 8, for the coordinator to log)
- **Stale comment, `core/resource_gate.py:1076`** — asserts "nothing in this
  codebase calls reserve_slot()/estimate_model_load_cost()", contradicted by the
  live call at `core/loader_v2.py:1450`. Misleading for exactly the
  process-lifecycle code CLAUDE.md rule 4 guards. Documentation-only; no
  behavior impact.
- **`core/memory_v2.py:5-22` module docstring overstates the system** — claims
  five working tiers and "RAG queries first hit the symbolic graph, then fetch
  language renderings" as present-tense fact. Tiers 2-5 are write-only, gated
  off, or dormant per §a.
- **`ccos/core/memory/ccos_memory.py`'s declared schema does not exist in
  `ccos/data/ccos_memory.db`** — the file holds only `performance_tracker`'s
  three tables. Two modules share one DB path (`ccos_memory.py:19`,
  `performance_tracker.py:20`, `telemetry_engine.py:30`) with disjoint schemas.

---

## (h) Open questions

1. **Why does `ccos/data/reflections.jsonl` have 235 KB and an mtime of
   2026-10-06 13:39 (today) when every reachable writer is demo/test code?**
   `ReflectionEngine.__init__` defaults to that path (`reflection_engine.py:56`)
   and `_save` appends (`:198`). `ccos/tests/test_ccos.py:240` and
   `test_goal_engine.py:53` pass temp paths, but `demo_goal_engine.py:45` uses
   `get_reflection_engine()` — the default path. Most likely a demo or an
   unredirected test run. Same question for `ccos/data/capabilities.json`
   (117 KB, mtime today — though that one has a live writer via
   `plugin_manager`/`capability_registry`, so it is probably legitimate).
   Worth 5 minutes to confirm no unnoticed process is writing these; not chased
   here to stay read-only and within budget.
2. **`cap_metrics` = 454 rows with no reachable writer.** `performance_tracker`
   is dormant per §d, yet the table is substantially populated. Were these
   written by demo/test runs against the real DB path
   (`performance_tracker.py:20` hardcodes it), or by a historical integration
   since removed? This matters because `capability_optimizer` and `goal_engine`
   would treat these rows as evidence if ever activated — stale or
   demo-generated metrics driving real promotion decisions is a live risk the
   moment the bridge in §d is built.
3. **Is the absent knowledge base intended?** `has_index()` = False and
   `$CODEY_DIR/knowledge` does not exist, so `retrieve()` returns `""` on every
   call and the `retrieval` and `skills` prompt layers are permanently empty.
   Is `tools/setup_skills.sh` meant to have been run (an install.sh gap, rule
   11), or has the KB been deliberately retired in favor of something else?
   This single fact silently disables the whole RAG path.
4. **Is `CODEY_SYMBOLIC` intended to stay off permanently?** 691 ln of
   `core/symbolic_graph.py` + the tier 4/5 write paths + `_run_symbolic_pipeline`
   hinge on one env var. If it is a retired experiment, say so; if it is
   pending, it needs a live-verify plan — note `_run_symbolic_pipeline`
   *replaces* `user_message` wholesale (`core/agent.py:1331-1332`), so enabling
   it changes every prompt, and `memory_v2.py` writes into `STATE_DB_FILE`
   (`symbolic_graph.py:100`) which is `~/.codeyOS/state.db` — shared with the
   live state store.
5. **Merge intent for `codey-os-dev-v2`.** `97ad62d` is a self-contained,
   test-covered improvement (+1264 LOC incl. 355 LOC of new tests) to the one
   measurement substrate rule 1 says must come first. Is it blocked, or just
   unmerged? Nothing in `main`'s ledgers inspected here explains the gap.
6. **Should the `ccos/` planner stack be integrated or retired?** This is a
   product-direction question, not an implementation detail (CLAUDE.md escalation
   criterion). ~6,500 LOC is either the multi-agent platform's future backbone or
   dead weight that makes every census and audit more expensive. It cannot be
   both.

---

## Status summary

| Area | Status |
|---|---|
| Memory tier 1 (Working) | **IMPLEMENTED** — written and read into prompts |
| Memory tier 2 (Project) | **PARTIAL** — write-only; prompt block comes from `core/codeymd.py` instead |
| Memory tier 3 (Long-term) | **DORMANT** — dead parallel embedding stack |
| Memory tier 4 (Episodic) | **PARTIAL** — content-free ticks only; never read back |
| Memory tier 5 (Symbolic) | **PARTIAL** — read-back wired; writes gated off by default |
| Session summary store | **DORMANT** — superseded by `core/summarizer.py` |
| `ccos_memory.py` | **DORMANT** — declared schema absent from its own DB |
| Context assembly (`layered_prompt`) | **IMPLEMENTED** |
| RAG pipeline | **PARTIAL** — code complete and reachable; corpus MISSING |
| KB ingestion | **DORMANT** — shell-script-only, never run here |
| Context ceiling / slot reservation | **IMPLEMENTED** (`loader_v2.py:1450`) |
| `core/` planner+orchestrator stack | **IMPLEMENTED** — canonical |
| `ccos/` planner+orchestrator stack | **DORMANT** — demos/tests only |
| `core/recursive.py` | **IMPLEMENTED** |
| CCOS reflection / goals / self-improvement | **DORMANT by design** (test-enforced invariant) + env-gated + bench-gated |
| Promotion gate (`bench/`) | **IMPLEMENTED** — but no production caller constructs a decision |
| Trajectory store (`main`) | **IMPLEMENTED**, truncating, default-off, 5 episodes |
| Trajectory store (`dev-v2`) | Full-fidelity + export hygiene — **NOT MERGED** |
| `core/symbolic_graph.py` | **IMPLEMENTED** but unreached in production (`CODEY_SYMBOLIC=0`) |
