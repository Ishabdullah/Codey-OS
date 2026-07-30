# Project Plan: Codey-OS (formerly Codey-v3 + CCOS, v4 retired)

**Status:** Active
**Started:** 2026-07-20
**Repo:** `Ishabdullah/Codey-OS` (new repo, seeded from Codey-v3, created 2026-07-27)
**Working directory:** `~/Codey-OS` on Termux/S24 Ultra
**Reference-only source:** `~/Codey-v4` (untouched, read from for migration only)
**Supersedes:** Codey-v4 Kernel migration project (retired as of this plan — see "What happened to v4" below)
**Authoritative spec:** `CODEY_OS_MASTER_VISION.md` — **signed off by Ish 2026-07-27.**
Every future decision, prompt, and restructuring step must not conflict
with it. Lives in the repo root; `QWEN.md` (repo root, once created) points
every fresh Qwen session to it.

---

## 1. Decision Summary

After auditing both Codey-v4's Kernel layer and Codey-v3's CCOS (Codey
Cognitive OS) subsystem against actual running code, we're changing the
base of future development:

- **Old plan:** Build outward from Codey-v4, with a custom Kernel
  (`ServiceRegistry` / `ManagerRegistry` / `DecisionEngine` / `PolicyEngine`)
  as the coordination layer for turning Codey into a pluggable-service
  platform.
- **New plan:** Build outward from **Codey-v3**, which already contains
  CCOS — a more complete, independently verified, six-layer cognitive
  architecture with capability registry, plugin system, sandboxed
  execution, multi-agent deliberation, and (not yet activated) self-
  improvement loops. Codey-v4 is retired as an active codebase. Its
  service-adapter pattern and any doc/changelog history worth keeping get
  migrated into this project; the Kernel classes themselves do not survive
  as the long-term routing mechanism.

**The end goal is unchanged from the original v4 vision:** a real
operating-system-like platform where coding is one pluggable capability
among several, with room to add more later, and — eventually, deliberately
— the ability for the system to begin improving itself. What changes is
which codebase we build that goal on top of.

---

## 2. What Happened to v4 (for the record)

- v4 added a Kernel layer on top of what is otherwise the same `core/` as
  v3. We fixed a blocking syntax error in `core/kernel.py` (unclosed `try`
  in `shutdown()`, duplicated dead code, missing `logging` import) and
  verified it compiles and instantiates.
- Two-pass code audit of v4 found only 2 of 12 claimed capabilities
  actually routed through the Kernel (RAG retrieval, three-model
  architecture via `conversation`/`memory`/`embedding` services). 2 more
  were partially routed (error recovery, peer CLI escalation). The
  remaining 8 (daemon, task queue, self-refinement, git, voice, static
  analysis, thermal management, fine-tuning export) were still direct-call,
  unmigrated.
- README.md was rewritten to accurately reflect this state (verified via
  literal diff, after two earlier attempts introduced unverified/fabricated
  content — a nonexistent "UnlimitedClaude" peer CLI and a fictional fourth
  model — which were caught and reverted).
- CCOS (in Codey-v3) was independently audited: all 19 core modules exist,
  compile clean, and **68 tests across 7 suites pass** on this machine,
  confirming it's substantially real, working code — not aspirational.
- `ccos/` and `core/` in Codey-v3 currently have **zero imports between
  them** — CCOS runs standalone via `ccos_main.py` and does not yet touch
  the coding-agent functionality in `core/`. That integration is the real
  work of this project.

---

## 3. Target Architecture

```
Codey-v3 (base)
├── ccos/                          ← becomes the OS layer
│   ├── core/capability_registry   ← replaces v4's ServiceRegistry
│   ├── core/plugin_manager        ← replaces v4's ManagerRegistry + adds real plugin discovery
│   ├── core/tool_router           ← replaces v4's DecisionEngine
│   ├── core/agent_orchestrator    ← replaces v4's PolicyEngine (Safety Agent veto)
│   ├── core/sandbox               ← new: isolated execution (v4 had none)
│   ├── core/[optimizer/recombiner/goal/project engines] ← present, NOT wired into
│   │                                                        live execution yet
│   └── plugins/                   ← coding-agent features get wrapped here
│       ├── coding/                ← from core/fixmode.py, core/agent.py etc.
│       ├── daemon/
│       ├── git/
│       ├── voice/
│       ├── thermal/
│       ├── finetune/
│       └── ...
└── core/                          ← existing coding-agent implementation, unchanged
                                       until wrapped as a plugin, one at a time
```

Governance moves from v4's `PolicyEngine` to CCOS's `agent_orchestrator`
Safety Agent veto (highest voting weight, can veto any plan) plus
`sandbox.py`'s enforcement rules (no destructive commands, no path escapes,
resource limits).

---

## 4. Phases

### Phase 0 — Foundation (this plan + log setup)
- [x] Audit v4 Kernel, fix `kernel.py`, verify README accuracy
- [x] Audit CCOS, confirm 68/68 tests pass
- [x] Confirm `ccos/` and `core/` are currently unconnected
- [x] Decide: build forward from v3+CCOS, retire v4
- [x] New repo `Codey-OS` created, seeded from Codey-v3, remote repointed
- [ ] Confirm disposition of `core/symbolic_graph.py` — exists in v3, was
      dropped in v4. Ask Ish whether this was intentional before deciding
      whether to keep it in the merged base.
- [ ] Migrate any still-accurate doc/changelog history from v4 into this
      project's docs (not a priority; do after Phase 1 stabilizes)

### Phase 1 — Wrap first coding-agent capability as a CCOS plugin (pilot)
**Status: COMPLETE (2026-07-28)**
Pick ONE feature to migrate first, end to end, to prove the pattern before
doing the rest. Candidate: RAG retrieval, since it's the one v4 feature we
confirmed was cleanly service-ified already (`embedding_service.py` /
`core/retrieval.py`), so there's a template to adapt from.
- [x] Confirmed real `core/retrieval.py` interface and real CCOS plugin
      pattern (manifest.json structure, test.py convention, auto-discovery)
      against actual source before writing the task prompt
- [x] Wrote `ccos/plugins/research/rag_retrieval/manifest.json` +
      implementation wrapping `core/retrieval.py`'s `retrieve()` as
      `research.retrieve` (reused the existing empty `research/` category
      rather than creating a new one — commit `028b4a6`)
- [x] Confirmed `plugin_manager` discovers and loads it — verified via
      real script: plugin count went from a known baseline of 6
      plugins/9 capabilities (cross-checked independently against the
      original repo audit) to 7/10, confirming clean addition
- [x] Confirmed the capability is queryable/invokable through
      `capability_registry` — `pm.call_capability('research.retrieve', ...)`
      returned correctly (empty string, graceful — KB has no matching
      content), use_count/success_count bumped on the registry entry
- [x] Existing direct-call path (`core/agent.py`,
      `prompts/layered_prompt.py`) confirmed untouched — `git diff --stat`
      empty on both
- [x] `test.py` added following the existing convention, 3/3 pass
- [x] Honest pattern assessment obtained: clean for ccos-internal plugins,
      but found a real bug — the copied `.parent` chain in every existing
      plugin's `test.py` lands on `ccos/` not the true repo root, silently
      shadowing top-level `core/` with `ccos/core/` (same package name,
      real collision risk) for any plugin importing from outside `ccos/`.
      Fixed locally with `parents[4]`, but flagged as needing a shared fix
      before repeating 9 more times (9 of 10 remaining capabilities live
      under `core/`/`tools/`/`utils/`/`pipeline/`).
- [x] **Follow-up complete:** shared `ccos/plugins/_pathutil.py` helper
      (commit `81a6b5f`) — anchors the walk-upward search at
      `_pathutil.py`'s own fixed location (2 levels below repo root)
      rather than the caller's, correctly sidestepping caller-nesting-
      depth entirely. `rag_retrieval` migrated to use it; regression-
      checked the one pre-existing sandbox test failure via `git stash`
      to confirm it predates this change.

### Phase 2 — Migrate remaining coding-agent capabilities
**Status: COMPLETE (2026-07-28) — 9 of 10 items wrapped, item 7 deferred**
One capability at a time, in this order (direct-call features first, since
they're simpler wraps than the partially-routed ones):
1. Static analysis (`core/linter.py`) — **COMPLETE**. Implementation
   commit `6c2c1b3`, blocking shared bug fixed in commit `fe00218`
   (verified via isolation testing: reverting the `_pathutil.py` hardening
   alone reproduced the exact original failure, confirming it was the
   load-bearing fix). Final state: 8/8 plugins loaded, 12 capabilities
   reconciled, sandbox test remains the sole pre-existing unrelated
   failure.
2. Git integration (`core/githelper.py`) — **COMPLETE** (commit `4921c24`).
   16 of 17 functions registered as capabilities (`uses_conventional_commits`
   correctly left internal — only called by `generate_commit_message`,
   confirmed via grep, not independently useful). Real mutating-operation
   test against a throwaway repo only (never this repo), specific evidence
   (commit hashes `2f470b1`/`8147828`). Capability count reconciled: 12→28.
   **Known gap:** 2 of 16 registered capabilities never actually invoked —
   `generate_commit_message` (needs 7B model, correctly deferred) and
   `git_push` (skipped over network-call ambiguity, though testable
   offline via two local throwaway repos — not done, low priority).
3. Voice interface (`core/voice.py`) — **COMPLETE** (commit `9d9d8b8`).
   Consolidated into the existing `tts_speech` plugin rather than creating
   a new one (one-plugin-per-domain, matching `system_info`/
   `camera_capture`) — TTS stays on `tts_speech`'s richer 4-engine
   fallback, STT added from `core/voice.py`. Found and fixed an
   independent manifest bug (`implementation: "tts:speak"` pointed at the
   filename, not the plugin's registered name — capability could never
   resolve through `plugin_manager`, reproduced pre/post-fix). `install.sh`
   gap closed (`pyttsx3`, `espeak`/`termux-api` now declared). STT
   end-to-end unverifiable in this headless environment (no real mic) —
   wiring confirmed, true transcription not, honestly disclosed.
4. Thermal management (`core/sysmon.py`, `core/thermal.py`) — **COMPLETE**
   (commit `0aac59e`). New plugin `thermal_monitor` (not extending
   `system_info` — different lifecycle, background-thread state vs.
   one-shot lookups). 8 capabilities: monitor snapshot/render, thermal
   status/throttle-check/thread-count (read-only), plus
   start_inference/end_inference/reset (mutating, mirroring
   `git_integration`'s pattern). Real live values confirmed (actual
   `/proc` reads: CPU%, RAM bytes, temp; `battery_pct: None` correctly
   reflects this device having no battery sysfs/Termux:API path, not a
   mock gap). Capability count 30→38 reconciled (initial apparent
   discrepancy was Claude's own tallying error misreading a combined
   table row as one capability instead of two — not stale registry
   state; confirmed directly via `git log -p` that `capabilities.json`
   has only 2 commits total, one touching only timestamps, never
   accumulating real drift).
5. Fine-tuning export (`core/finetune_prep.py`, `core/lora_import.py`) —
   **COMPLETE, deliberately partial scope.** 7 safe capabilities wrapped
   (dataset curation/export, notebook generation, adapter
   validation/info — all generative or read-only). The 5 functions that
   directly swap/merge the live model file
   (`swap_to_finetuned_model`, `merge_lora_with_llama_cpp`,
   `create_backup_before_import`, `rollback_to_backup`,
   `import_lora_adapter`) were **deliberately left unwrapped** — real,
   well-reasoned risk distinction from git's mutating capabilities (no
   cheap undo via a separate system; a bad swap breaks the only model the
   whole system runs on; making it agent-callable risks a live-model swap
   as a side effect of planning, not just deliberate human action via the
   existing `--import-lora` CLI path, which remains the only way to
   trigger these). **Open question for Ish:** whether
   `create_backup_before_import`/`rollback_to_backup` should be added
   later. **Resolved: yes, add both** — done (commit `43c5ba7`), 47
   capabilities total. Discovered and correctly handled a subtle safety
   issue during testing: `rollback_to_backup` reloads via
   `core.loader_v2.get_loader()`, which binds the model path at import
   time — a plain `cfg.MODEL_PATH` monkeypatch alone would NOT have
   prevented it from touching the real model. Dual-patched both
   `cfg.MODEL_PATH` and `loader_v2.get_loader` (no-op fake loader),
   restored in `finally`. Verified via SHA-256 checksums that backup was
   byte-identical and rollback restored original content exactly.
6. Task queue (`core/taskqueue.py`) — **COMPLETE** (commit `dea2aaf`).
   Path-addressable design (queue JSON path passed to every capability
   call, load/save per call, no in-memory instance cache — avoids a
   redundant second source of truth alongside the file). 7 capabilities:
   create/add/mark_running/mark_done/mark_failed/status/list.
   `plan_tasks()` correctly left as `orchestrator.py`'s own concern (a
   compound LLM-driven operation, not thin persistence). Real disk
   persistence proven via actual JSON read-back; confirmed no test
   artifacts left in `~/.codey_sessions/`. 47→54 capabilities reconciled.
7. Recursive self-refinement (inside `core/agent.py`) — **DEFERRED, not
   skipped.** Doesn't fit the standalone-utility-wrap pattern the previous
   6 items used — it's part of the still-unwrapped "Coding agent (core
   intelligence)" primary capability (master vision Section 3), not a
   peripheral one. Will be tackled together with wrapping the actual
   coding agent itself, as its own dedicated, carefully-scoped task later
   in Phase 2 — not now, and not to be silently dropped. **Testing note
   for when we get there:** rather than loading the real 7B model (RAM
   risk — already caused one crash during earlier planner-fix
   verification), consider swapping in a much smaller model
   (e.g. the 1.5B planner model, or an even smaller test model) purely
   for exercising the self-refinement/tool-calling mechanics during
   development — Codey-OS can't have a full coding-agent-sized model
   running for testing purposes on top of its own already-running model
   stack (7B + 1.5B + embedding) without risking the same OOM crash.
8. Daemon mode (`core/daemon.py`, `main.py:_daemon_is_running()`) —
   **COMPLETE, deliberately partial scope** (commit `874c748`). 7 safe
   capabilities under `system.daemon_*` (category `system`, not `coding`
   — process/liveness management, same class as `thermal_monitor`).
   `shutdown` and `command` (real task-submission, triggers actual 7B
   inference) deliberately left unwrapped — same risk-class reasoning as
   `swap_to_finetuned_model`. Tested the socket protocol layer safely by
   starting a bare `DaemonServer` (not the full `Daemon` class, no model
   loading) on a temp socket — confirmed the socket layer itself is
   lightweight independent of model loading. 54→61 capabilities
   reconciled.
9. Error recovery (`core/recovery.py`) — **COMPLETE, standalone scope**
   (commit `0132e0f`). 4 capabilities: `classify_error`, `get_fallback`,
   `execute_strategy`, `record_outcome`. Overlap with
   `core/strategy_tracker.py` confirmed real and resolved at the plugin
   layer — `StrategySwitcher`'s own tracking (in-memory, capped at 100
   entries, zero callers) deliberately NOT wrapped; `recovery_record_outcome`
   routes through the already-persisted, already-used `StrategyTracker`
   instead, without modifying `core/recovery.py`'s source. Found and
   honestly documented a real pre-existing classification bug in
   `recovery.py` ("command not found" misclassifies as `file_not_found`).
   `execute_strategy` tested live only for the safe mkdir path;
   pip-install/pytest-isolation paths correctly left unexecuted during
   testing. Not wired into `agent.py`'s failure path — deferred with item
   7. 61→65 capabilities reconciled.
10. Peer CLI escalation — **COMPLETE, safest possible scope**
    (commit `ef57fed`). Found the real consent mechanism
    (`PeerCLIManager.confirm()`, a blocking interactive terminal prompt)
    and correctly concluded it has no automated-call equivalent —
    `escalate`/`confirm`/`call`/all of `peer_shell.py`'s invocation
    functions left completely unwrapped. 4 genuinely safe read-only
    capabilities exposed instead (list available CLIs, task-type
    detection, dry-run CLI selection, prompt preview without sending).
    Confirmed no real external CLI was invoked during testing — only
    `shutil.which` checks and one caught local exec failure (broken
    `claude` shebang in this environment, not an invocation). 65→69
    capabilities reconciled.

**Phase 2 summary:** 9 of 10 original items fully wrapped (item 7,
recursive self-refinement, deliberately deferred — see log). Consistent
risk-tiered judgment held across all mutating/external-facing functions
throughout — nothing risky was wrapped mechanically just because the
established pattern said "wrap it." All deliberately-unwrapped items
consolidated in `PENDING_ISH_DECISIONS.md`. One gap found and flagged
during the final reflection: `core/observability.py`'s wrap was never
actually scheduled anywhere in this list — needs its own task.

Each item gets its own checklist (manifest, registration, routing test,
CCOS test suite entry) mirroring Phase 1's pilot.

### Phase 3 — Unified entry points + retire old fragmented ones
**Status: STARTING** (per `CODEY_OS_MASTER_VISION.md` Section 6a)

Breaking into two sub-steps, same incremental philosophy as Phase 1/2
(add new alongside old, prove it, retire old separately — not a risky
big-bang replacement):

**Sub-step A — COMPLETE (commit `4477a5c`).** `codey-start` shells out to
`codeyd3 start`, reuses `codey3`'s existing GUI-PID-file coordination
mechanism (`$HOME/.codey-v3/gui-server.pid`, confirmed pre-existing in
`codey3` lines 397-415, not new). Daemon deliberately persists after TUI
exit (daemon mode's purpose — avoid repeated model-load cost);
`codey-start`'s cleanup trap only tears down what it uniquely owns (the
GUI it started). `codey-stop` confirmed via real process checks: daemon +
plannd + GUI + all 3 model servers cleanly stopped, zero orphaned
`llama-server` processes. `codey3`/`codeyd3`/`ccos_main.py`/`gui/start.sh`
confirmed byte-for-byte unchanged. `install.sh` updated (PATH check,
completion banner). **Minor open item:** a race-condition fix (`sleep
0.5` before an orphan-process pgrep check) was syntax-checked but not
live-tested, per RAM discipline — worth confirming on a future live run,
low priority.
- [x] `codey-start` brings up the daemon + TUI + GUI together, per the
      master vision (both interfaces can run simultaneously)
- [x] `codey-stop` cleanly shuts down daemon + TUI + GUI + any model
      servers
- [x] Existing `codey3`/`codeyd3`/`ccos_main.py`/`gui/start.sh` remain
      untouched and working during this step

**Codey-OS branding rename — COMPLETE (5 sub-tasks, final commit
`94b7b9b`).** Discovered mid-Sub-step-A while testing `codey-start`;
`codey3`/`codeyd3` themselves and ~90 other files still carried
"Codey-v2"/"Codey-v3" branding and naming, a real risk given this exact
pattern had already caused bugs twice. Executed as its own sequenced
5-part effort rather than one sweep, given 93 files / 463 occurrences:
1. Shared path-constant foundation (`utils/config.py`), behavior-
   preserving refactor before any renaming — commit `9e86a9c`
2. Actual file renames (`codey3`→`codeyOS`, `codeyd3`→`codeydOS`),
   constant value flip, cross-references — commit `147aafd`
   (paused mid-sequence for a real investigation — see below)
3. Cosmetic branding sweep, ~320 occurrences, plus bundled fixes (GUI
   version badge bug, HTTP-Referer headers) — commit `702b0d5`
4. Docs filename, CHANGELOG entry, remaining functional filename
   references — commits `9ec73b1`/`9dcf7a7`
5. Lowercase command-name sweep, closing a gap in sub-task 4's own
   verification grep (`main.py`'s `/help` was telling users to run a
   dead command) — commit `94b7b9b`

**Real bugs found and fixed along the way (not just branding):**
`codey3`/`codeyd3` daemon-directory mismatch (couldn't detect the real
daemon at all), GUI crash on Ctrl+C during active generation, 3
checkpoint-system bugs (`is_core_file()` scope was the entire repo not
just core dirs; `git add -A` over-staging; a test-isolation bug),
`/usr/bin/env` shebang failures (Termux-specific), orphaned
`llama-server` processes surviving `stop` (plausibly explains
unexplained high baseline RAM from early in this project). All verified,
all fixed, all logged in detail in `PROJECT_LOG.md`.

**Deliberately left alone, tracked not forgotten:**
`docs/tools-embedding-pipeline.md`'s prose content still narrates
"Codey-V3" throughout (only its filename was fixed — a content-accuracy
question, not a stale-reference one); a telemetry dedup-key collision bug
found during verification (`ccos/core/telemetry_engine.py`, causes
intermittent test flakiness, real pre-existing bug, unrelated to the
rename — fix later: `uuid.uuid4()` or an atomic counter instead of
timestamp+`id()`).

**Sub-step B — COMPLETE (commit `03182e9`).** New shared
`core/dashboard_data.py` module, imported by both TUI (`main.py`) and GUI
(`gui/server.py`) — avoids duplicating capability-call/plugin-manager
bootstrap logic in two places. `sysmon.py`'s rendering logic extracted so
it works from any snapshot dict; GUI's `get_ram()` now sources from the
same shared module instead of parsing `/proc/meminfo` independently.
Verified via simultaneous capture: TUI and GUI showed matching
`ram_total` with only expected small timing-drift on `ram_used` — genuine
same-source proof, not just "both work independently." Zero llama-server
process during the OpenRouter-only test run, zero orphaned processes
after stop.
- [x] Wire `thermal_monitor` (system-wide CPU/RAM/temp/battery, Phase 2
      item 4) and `observability` (process-specific tokens/memory/tasks/
      health, just completed) capabilities into both the TUI's status bar
      and the GUI's display, so they read from the same source and never
      diverge — this is the literal "Unified system dashboard"
      requirement from the master vision

**Sub-step C — COMPLETE (commit `314450a`).** Discovery: the file at
`README.md` was never actually a project README — it was the internal
CCOS architecture doc (12 sections, 6-layer diagram, module tables) from
very early in this project, sitting at that filename the whole time.
Genuine rewrite, not an update: 143 insertions, 365 deletions. Correctly
caught and fixed a real overclaim in the old content (a table flatly
stating "Self-improving: Yes," contradicting Section 5's gated-by-default
reality) rather than carrying it forward. Section-by-section accounting
done for all 12 old sections + License. Independent code audit (required,
not just doc cross-checking) found `docs/commands.md` missing 12 real
slash commands and ~13 real CLI flags that exist in `main.py`, plus one
possibly-stale flag (`--rollback`) — correctly left unfixed (out of
scope) but flagged, with the README's own description of
`docs/commands.md` softened so it doesn't inherit the overclaim.
**Real process gap found:** confirmed `PROJECT_PLAN.md` and
`PENDING_ISH_DECISIONS.md` were never actually committed to the repo —
only ever handed back as downloadable files. Being fixed now (see below).
- [x] Restructure README around: what Codey-OS actually is now (CCOS
      shell + coding-agent capabilities, not a standalone coding tool),
      the unified `codey-start`/`codey-stop` entry points, the 10 wrapped
      capabilities, the unified dashboard (once Sub-step B lands), and
      accurate Quick Start instructions using the real current command
      names
- [x] Cross-check against `CODEY_OS_MASTER_VISION.md` Section 3 as
      primary source, verify against actual code only where something
      seems uncertain or possibly stale (same discipline as everything
      else this project — don't just trust a doc, spot-check)
- [x] Decide what to do with the now-fixed-but-still-stale-feeling
      "Codey-v2/v3 era" framing throughout — resolved by the full
      rewrite; the rename itself gets one honest mention in the intro

**Two loose threads tracked, not blocking Phase 3 closure:**
1. `docs/architecture.md` still only documents the coding agent's
   three-model design, no CCOS-layer content — already a known gap noted
   in the master vision as a planned rewrite, not new.
2. `docs/commands.md`'s incompleteness (found above) — worth a dedicated
   follow-up, since the new README now points readers there specifically.

**Then, once B and C are both proven stable:**
- [ ] Decide fate of `main.py` (v3's original direct entry point) — keep
      as a thin compatibility shim, or fully retire
- [ ] Retire `codey3`/`codeyd3`/`ccos_main.py`/`gui/start.sh` as the
      user-facing surface (underlying pieces may remain, orchestrated by
      the new scripts, per master vision Section 6a)
- [ ] Confirm nothing still depends on v4's `core/kernel.py` pattern
      before archiving it (should already be true, v4 was never part of
      Codey-OS's lineage)

### Audit Remediation — Round 1 (C-1, H-1, H-4)
**Status: H-4 FIXED AND LIVE-VERIFIED. C-1 FIXED AND LIVE-VERIFIED (short
QA prompt landed as a follow-up). H-1 still mechanism-verified only — no
live check of the shutdown path has been run.** (2026-07-29) — fixes from
`Codey-OS-audit.md`'s Critical finding C-1 and High findings H-1/H-4, the
three causally-linked issues behind the "Codey doesn't respond" live
symptom (slow first response → impatient retry → daemon-race → killed
model server). Round 1's H-4 fix (writing the daemon's own PID early)
introduced a self-race bug — the daemon always found its own PID in
`check_pid_file()` and refused to start — which is why the first live
verification attempt failed outright; that self-race is now also fixed
and confirmed live. C-1's original fix only tiered the *code paths*, not
the prompt content — the "identity" block was still the full
8,352-char tool-format prompt even on the lightweight path; a follow-up
(`get_qa_system_prompt()`) now actually shrinks it. See `PROJECT_LOG.md`
2026-07-29 entries (both the original Round 1 entry and the follow-up
above it) for full detail.
- [x] **C-1** — Tiered the system prompt: `is_qa` classification moved
      before prompt construction in `core/agent.py`, threaded into
      `build_recursive_prompt()`/`_build_draft_prompt()` as a new
      `lightweight` param (`prompts/layered_prompt.py`) that skips the
      repo_map/retrieval/skills/files/symbolic_graph code paths entirely
      for QA/smalltalk messages. Added an elapsed-time "Thinking... (Ns,
      processing N-token prompt)" ticker in `core/inference_v2.py` for the
      prompt-processing window, threaded via an `on_first_token` callback
      through `core/inference_hybrid.py` and `core/inference_openrouter.py`
      so it clears cleanly the instant real output starts streaming.
- [x] **H-1** — Removed `main.py`'s blanket `pkill -9 -f llama-server`
      shutdown fallback. `core/loader_v2.py`'s `ModelLoader` gained a
      `get_pid()` accessor; `main.py`'s `shutdown()` now captures that PID
      before calling `unload()` and, only if `unload()` itself throws,
      falls back to killing that one PID's process group — never a bare
      name pattern.
- [x] **H-4** — `codeydOS`'s `start_daemon()` now writes the PID file
      (atomic write-then-`mv`) immediately after capturing `$DAEMON_PID`,
      from the shell itself, instead of waiting for `core/daemon.py`'s own
      later `write_pid_file()` call. Closes the race where a concurrent
      `codeydOS start` during the 7B's load window passed the stale/absent
      PID guard and pre-killed the first instance's loading model server.
      Also cleans up the PID file on the daemon-failed-to-start path (a new
      failure mode introduced by writing it earlier).
- [x] **H-4 self-race fix** — `check_pid_file()` in `core/daemon.py` now
      returns `False` (not a duplicate) when the PID in the file is its
      own, since Round 1's fix made that the expected case on every
      startup. Live-verified: `codeydOS start` succeeds cleanly, a
      concurrent `codeydOS start` during model load correctly reports
      "already running" and does not kill the loading instance
      (confirmed exactly one `llama-server` PID via `pgrep` once loading
      finished).
- [x] **C-1 follow-up: short QA identity prompt** — added
      `get_qa_system_prompt()` (`prompts/system_prompt.py`, ~280 chars,
      no tool-format instructions) and wired it into
      `_build_draft_prompt()`'s `identity` layer for `lightweight=True`.
      Lightweight prompt dropped from 8,947 → 849 chars. Live-verified in
      a single warm session: QA turns ("hello", "what can you do?") both
      returned plain text with no `<tool>` leakage in ~14-20s
      first-token time; a real coding request in the same session
      correctly took the full path (file loaded, recursive draft/review,
      tool call generated). See `PROJECT_LOG.md` for the full numbers and
      the caveat that the ~15s-vs-~180s comparison isn't a clean
      isolation of the char-count savings alone (warm vs. cold session).
- [ ] **H-1 live verification — NOT YET DONE.** Only C-1 and H-4 got a
      real live check this round. H-1 (scoped process kill on shutdown)
      is still verified at the mechanism level only (`get_pid()` exists,
      the blanket `pkill` is gone) — nobody has yet triggered the
      `unload()`-throws fallback path live and confirmed it kills only
      the one captured PID's process group.

### Audit Remediation — Round 2 (C-2)
**Status: FULLY LIVE-VERIFIED** (2026-07-29) — fix from
`Codey-OS-audit.md`'s Critical finding [C-2] (GUI server: unauthenticated
command execution, bound to `0.0.0.0` by default, no WebSocket Origin
check). Three sub-tasks, each committed and code-reviewer-approved
separately, then confirmed end-to-end by a live-verifier pass through the
real `gui/start.sh` launch path. See `PROJECT_LOG.md` 2026-07-29 entries
for full detail.
- [x] Default GUI bind host changed `0.0.0.0` → `127.0.0.1`
      (`CODEY_GUI_HOST` env override preserved) — commit `d29468f`
- [x] `handle_ws` rejects connections with missing or mismatched `Origin`
      header (allowlist: `http://localhost:<port>` /
      `http://127.0.0.1:<port>`, port read from module-level `PORT`, not
      hardcoded) — commit `ca94ab5`
- [x] Per-process session token (`secrets.token_urlsafe(32)`) required as
      a query param on the `/ws` upgrade, timing-safe comparison,
      independent AND with the Origin check, both checked before
      `ws.prepare()`. `GET /` intentionally left ungated (loopback-only,
      no real second security boundary to gain) — commit `1198ba1`
- [x] Verified by code-reviewer against a real running instance on a
      scratch port: all 4 token/Origin combinations behaved as expected
      (no-token 403, wrong-token 403, correct+correct 101,
      correct-token+bad-Origin 403), clean PID-tracked teardown
- [x] **Fully live-verified through the actual `gui/start.sh` launch
      path** (real daemon startup, not a scratch instance). Model load
      confirmed (7B, PID 25675, `/health` → 200). Loopback-only bind
      confirmed via direct connectivity: `127.0.0.1:8888` → 200, real LAN
      IP `192.168.1.111` → connection refused on both 8888 and 8080. WS
      auth re-checked against the real served token (fetched live from
      the actual `index.html`, not reused): missing Origin → 403,
      correct Origin + wrong token → 403, correct Origin + missing token
      → 403, correct Origin + correct token → 101 + real metrics
      broadcast frame. All 5 real processes (`gui/server.py`,
      `llama-server`, `main.py`, `start.sh` wrapper, plus the test
      harness's FIFO-holder helper) torn down individually by tracked
      PID. `free -h`: 4.0Gi used pre-launch → 3.4Gi used post-teardown
      (healthier than baseline). Single model-load cycle, confirmed
      unloaded. See `PROJECT_LOG.md` for full numbers.
- Follow-up logged, not fixed: `NEW_ISSUES.md` [NEW-3] (Suspected) —
  GUI session token could leak into access logs if logging is ever
  configured for `gui/server.py` (dormant today).
- New follow-up logged during this live-verification pass:
  `NEW_ISSUES.md` [NEW-4] (Confirmed) — `gui/start.sh` unconditionally
  chains into `main.py`, forcing a full 7B model load with zero user
  interaction just to view the dashboard.

**Round 2 (C-2) is now fully closed** — all 3 sub-tasks committed and
code-reviewer-approved, plus a full live-verifier pass through the real
launch path. No open items remain under Round 2.

### Audit Remediation — Round 3 (NEW-4)
**Status: FULLY LIVE-VERIFIED** (2026-07-29) — fix for `NEW_ISSUES.md`
[NEW-4], found during Round 2's live-verification pass: `gui/start.sh`
unconditionally chained into `main.py`, forcing a full 7B model load with
zero user interaction just to view the dashboard.
- [x] Added an opt-in `--dashboard-only` flag (or
      `CODEY_GUI_DASHBOARD_ONLY=1` env var) to `gui/start.sh` that skips
      `main.py` entirely and waits on the GUI server's own PID instead,
      reusing the existing trap/kill logic unchanged (no second kill
      path introduced). Default (no-flag) behavior byte-for-byte
      unchanged. Commit `ea954eb`.
- [x] code-reviewer approved, with one non-blocking suggestion: the new
      arg-parsing loop makes the last non-flag positional arg win
      instead of the first — latent, no current caller passes multiple
      positional args, not required to fix before merge.
- [x] Live-verified both paths directly:
      - Default path: real model-load cycle observed (`free -h`: 8.3Gi
        used during load → 3.1Gi used after teardown), `main.py` +
        `llama-server` both running as before, confirmed unloaded after
        stop.
      - `--dashboard-only` path: `pgrep` confirmed no `main.py`/
        `llama-server` process ever started; `curl` to the dashboard
        returned 200. Teardown by tracked PID clean in both cases.
      - Single model-load cycle run for this round, confirmed unloaded
        afterward per RAM-discipline rule.
- Follow-up logged, not fixed: `NEW_ISSUES.md` [NEW-5] (Suspected) — a
  `llama-server` child possibly briefly outliving `gui/start.sh`'s parent
  on a mid-load `TERM` kill, observed once during this round's default-
  path verification. code-reviewer confirmed it's unrelated to this
  round's diff (lives in `main.py`'s own spawn/kill path, untouched here,
  and unreachable in `--dashboard-only` mode).

**Round 3 (NEW-4) is now fully closed** — code-complete, code-reviewer-
approved, and live-verified on both the default and `--dashboard-only`
paths. No open items remain under Round 3 itself; [NEW-5] is a separate,
unscoped follow-up tracked in `NEW_ISSUES.md`.

### Audit Remediation — Round 4 (NEW-3)
**Status: CODE COMPLETE, code-reviewer-approved** (2026-07-29) — fix for
`NEW_ISSUES.md` [NEW-3], found during Round 2 (C-2) sub-task 3's review:
the GUI session token could leak into aiohttp's default access log if
`logging.basicConfig()` (or any handler) is ever configured for
`gui/server.py`'s process in the future — dormant, not currently
exploitable, but fragile.
- [x] `gui/server.py`'s `web.run_app()` call now passes `access_log=None`,
      disabling aiohttp's default `AccessLogger` outright. Commit
      `efe9f5c`.
- [x] code-reviewer approved: confirmed `access_log` is a genuine
      documented `aiohttp` kwarg (aiohttp 3.14.3 installed), verified no
      other log call site in `gui/server.py` could leak the token.
- No live-verification performed for this fix specifically — scoped as a
  negative/absence assertion with no new live-session behavior to
  exercise, already covered by Round 2 (C-2)'s prior full live
  verification of normal GUI start.

**Round 4 (NEW-3) is now fully closed** — code-complete and
code-reviewer-approved. No open items remain under Round 4 itself.

### Audit Remediation — Round 5 (NEW-1)
**Status: FULLY LIVE-VERIFIED** (2026-07-29) — fix for `NEW_ISSUES.md`
[NEW-1], root-cause Confirmed in Round 5's diagnostic investigation:
`pytest tests/` spawned a real 7B `llama-server` and orphaned it because
`tests/test_memory.py::TestMemoryCompressSummary::test_compress_summary_handles_inference_failure`
called `compress_summary()` with no mocking of inference at all.
- [x] `tests/test_memory.py`'s
      `test_compress_summary_handles_inference_failure` now mocks
      `core.inference_v2.infer` to return the real failure-return
      convention, and asserts the actual failure-path fallback behavior.
      Commit `c65be95`.
- [x] code-reviewer approved: independently re-ran both the targeted test
      and the full `tests/test_memory.py` file, confirmed no orphan
      `llama-server` after either.
- [x] **live-verifier ran the full suite**: `pytest tests/ -q` → 253
      passed in 0.43s (previously ~42s due to the hidden real model
      load). No orphan `llama-server` after (`ps -eo pid,ppid,comm | grep
      llama`, clean — `pgrep -af` avoided due to a false-positive
      self-match issue in this shell). `free -h` stable before/after
      (563Mi→816Mi free, swap unchanged at 1.6Gi). `NEW_ISSUES.md`
      [NEW-1] updated to Resolved.

**Round 5 (NEW-1) is fully closed.** Both code-complete and live-verified
criteria are met per Ground Rule 7.

### Audit Remediation — Round 6 (NEW-5)
**Status: FULLY LIVE-VERIFIED** (2026-07-30) — fix for `NEW_ISSUES.md`
[NEW-5]: `llama-server` could be orphaned indefinitely if `SIGINT`
landed while the model was still loading in `main.py`'s `repl()`,
because `KeyboardInterrupt` is a `BaseException` not caught by
`loader_v2.py`'s `load_primary()`'s own `except Exception`, and
`llama-server` is spawned with `preexec_fn=os.setsid`, insulating it
from the terminal's signal group.
- [x] `main.py`'s `repl()` (~line 1267-1274) wraps `loader.load_primary()`
      in `try/except (KeyboardInterrupt, SystemExit)`, calling the
      existing `shutdown()` (~line 125-144, unchanged) and returning
      cleanly. No new kill path introduced. Commit `eed29dc`.
- [x] code-reviewer approved, with one Warning: live-verification output
      wasn't yet recorded in `PROJECT_LOG.md` at approval time.
- [x] **live-verifier independently reproduced a genuine mid-load
      `SIGINT`** via `pty.fork()` (tracked child PID, not `timeout`, not
      a name-pattern kill), sent directly to the tracked PID before
      `llama-server` finished loading. Result: clean "Interrupted during
      model load, cleaning up..." message, `shutdown()` ran, and
      `ps -eo pid,ppid,pgid,comm | grep -E "python|llama"` was empty
      afterward — no orphan. `free -h` recovered from 3.3Gi used/4.3Gi
      free (mid-teardown) baseline of 4.2Gi used/892Mi free. An earlier
      backgrounded attempt was voided by live-verifier itself as
      inconclusive (model loaded before the `SIGINT` command ran) and
      not counted as a pass.
      - Regression check (normal-completion cycle, sequenced after the
        model was confirmed unloaded): full model load, one real
        inference exchange, clean `/exit` — no orphan process, RAM fully
        recovered (2.7Gi used/6.0Gi free after).
      - Single model-load cycle boundary respected: Test 2 only started
        once Test 1's `llama-server` was confirmed fully unloaded.
- [x] `NEW_ISSUES.md` [NEW-5] updated to Resolved, citing `eed29dc` and
      this live-verification.

**Round 6 (NEW-5) is now fully closed** — code-complete, code-reviewer-
approved, and independently live-verified (a real live-verifier
confirmation, not implementer-reported or code-complete-only evidence),
per Ground Rule 7. Of the user's original four-item punch list, NEW-3,
NEW-1, and NEW-5 are now all done. `NEW_ISSUES.md` [NEW-6] (same
unguarded pattern at three sibling call sites: `args.init` ~line 1458,
`args.tdd` ~line 1465-1466, `args.fix` ~line 1485-1486) remains open,
Suspected, unscoped — not fixed as part of this round. **NEW-2 remains
as Round 7, the hardest and final item on the punch list.**

### Audit Remediation — Round 7 (NEW-2)
**Status: CODE COMPLETE, code-reviewer approved** (2026-07-29/30) — fix
for `NEW_ISSUES.md` [NEW-2]. Root cause was corrected twice during
investigation (per Ground Rule 6) before landing on the confirmed
mechanism: live-verifier reproduced the bug live with the real 7B model
and found it is **not** a JSON-parse failure and **not** a false
success claim, but a **patch-application failure** — the `[Recursive]`
planner emits a well-formed `patch_file` call with `old_str=""` and a
whole duplicate `shutdown()` function as `new_str`; `tools/patch_tools.py`
correctly rejects it (existing guard since commit `8ab96e1`); the retry
budget (`max_retries(1)`) is exhausted on an identical second attempt
with no second warning printed; peer-CLI escalation is unavailable and
returns `None`; the loop falls through to a generic fallback that
re-invokes the model, which then asks an honest clarification question
instead of surfacing that the edit never applied. `git diff main.py`
confirmed empty (`shutdown()` at `main.py:125` unmodified) — the
silent no-op.
- [x] `core/agent.py`'s fallthrough branch (~line 1831+, after retries
      and escalation are both exhausted for a `write_file`/`patch_file`/
      `append_file` call still in an error state per `is_error()`) now
      logs and transcribes an explicit `[EDIT NOT APPLIED] <tool> on
      <path> failed after retries and escalation were exhausted — no
      file was modified.` marker before the generic fallback turn.
      Added `tests/test_new2_edit_not_applied.py`. Commit `55e408c`.
- [x] code-reviewer independently ran `git diff`, traced
      `last_tool_result`'s per-iteration freshness (reassigned every
      loop iteration — no staleness risk), confirmed the new test's
      `infer` monkeypatch targets the real module-level import at
      `core/agent.py:9` (explicitly checked against — and confirmed
      distinct from — the NEW-1 deferred-import-mismatch bug class),
      ran the targeted test itself (`1 passed in 0.19s`) and the full
      suite itself (`321 passed, 1 failed` — the one failure being the
      pre-existing, unrelated `ccos/tests/test_ccos.py::test_sandbox`,
      in a file this diff never touches). Approved, no Critical or
      Warning findings. One non-blocking Suggestion logged (pre-existing
      `("write_file", "patch_file")` tuple at `core/agent.py:1671`
      excludes `append_file`, unlike the new marker code's three-tuple —
      not fixed here, own future ticket).
- [ ] **Not live-verified with the real model post-fix.** The pre-fix
      bug reproduction was live (real 7B model); the post-fix
      confirmation is via code-reviewer's static/control-flow analysis
      plus mocked-test verification only, which is the appropriate bar
      for a logging/control-flow change (not a process-lifecycle
      change requiring live-verifier per Ground Rule 4/7). Not marked
      "live verified" per Ground Rule 7.

**Round 7 (NEW-2) is code complete and code-reviewer-approved — this
closes the final item of the user's original four-item punch list
(NEW-3, NEW-1, NEW-5, NEW-2), all now resolved.** `NEW_ISSUES.md`
[NEW-6] (sibling `load_primary()` gap) and [NEW-7] (recursive planner
synthesizing whole functions instead of targeted patches) remain open,
both Suspected/unscoped, discovered along the way but not originally
requested.

### Phase 4 — Self-improvement activation (deliberate, not automatic)
Do NOT start this phase until Phases 1–3 are stable and you've watched the
system run real coding tasks through the sandbox/safety-veto path for a
meaningful period.
- [ ] Review `auto_improvement_loop.py` and `capability_optimizer.py`
      behavior in a controlled test, not live
- [ ] Review `skill_recombiner.py` — decide what "compound skill" creation
      should require before it's allowed to register something new
      automatically (approval gate?)
- [ ] Review `goal_engine.py` — decide whether generated goals require
      explicit approval before entering the planner queue, at least
      initially
- [ ] Only after explicit sign-off, wire these into the live execution path

---

## 5. Open Questions (need your input before proceeding)

1. ~~`core/symbolic_graph.py` disposition~~ **Resolved 2026-07-27:**
   confirmed it's real, active code (691 lines, compiles clean) — a
   SQLite-backed concept-graph module actively imported by `core/agent.py`,
   `core/memory_v2.py`, `core/finetune_prep.py`, the fine-tuning exporter,
   and `prompts/layered_prompt.py`. It's load-bearing, not dead code.
   **Decision: keep it.** It was apparently dropped from v4 without being
   a deliberate decision — worth treating as a caution about doing
   file-by-file deletion carefully rather than by inference.
2. ~~Do we rename the project?~~ **Resolved 2026-07-27:** new repo created
   as `Codey-OS`.
3. Confirm Phase 1's pilot choice (RAG retrieval) makes sense to you, or
   would you rather pilot with something else first?

---

## 6. Ground Rules (carried over from your standing preferences)

- Every code change comes with a clear explanation and your approval
  before anything is written — no exceptions.
- All code must run on Termux/S24 Ultra; anything needing more compute
  gets flagged with GitHub/Colab/Kaggle options.
- Claude writes precise instructions for Qwen; Qwen's output gets reviewed
  for fabrications before being trusted (per the earlier README incidents
  in this same project — Qwen invented a fake CLI and a fake model once
  already, so every migration step's completion claim gets checked against
  a real diff or test run, not just Qwen's summary).
- This plan and the accompanying log get updated after every meaningful
  change, not just at phase boundaries.
